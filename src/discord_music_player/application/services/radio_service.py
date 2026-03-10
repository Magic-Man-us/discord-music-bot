"""AI-powered radio: pool-based recommendation system with batch fetching.

Architecture:
- toggle_radio() fetches batch_size(10) recommendations from AI
- Resolves visible_count(3) immediately and enqueues them
- Remaining 7 go into the unresolved pool on RadioState
- replenish_from_pool() pops from pool → resolve → enqueue (called on track consumed)
- When pool empties, publishes RadioPoolExhausted → triggers "Continue?" prompt
- continue_radio() fetches a fresh batch and refills the pool
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.music.entities import GuildPlaybackSession, Track
from ...domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
    filter_duplicates,
)
from ...domain.shared.events import RadioPoolExhausted, get_event_bus
from ...domain.shared.types import (
    DiscordSnowflake,
    NonEmptyStr,
)
from .radio_models import RadioState, RadioToggleResult

if TYPE_CHECKING:
    from ...config.settings import RadioSettings
    from ...domain.music.repository import SessionRepository, TrackHistoryRepository
    from ..interfaces.ai_client import AIClient
    from ..interfaces.audio_resolver import AudioResolver
    from .queue_service import QueueApplicationService

logger = logging.getLogger(__name__)

_REROLL_CANDIDATES: int = 3
_SMART_SEED_LIMIT: int = 5  # Number of recent tracks used for session-aware seeding


class RadioApplicationService:
    """Orchestrates the radio feature using a pool-based recommendation pipeline.

    Flow: AI batch(batch_size) → resolve visible(visible_count) → pool(remainder)
    → auto-replenish from pool → prompt on pool exhaustion → continue or stop.
    """

    def __init__(
        self,
        *,
        ai_client: AIClient,
        audio_resolver: AudioResolver,
        queue_service: QueueApplicationService,
        session_repository: SessionRepository,
        history_repository: TrackHistoryRepository,
        settings: RadioSettings,
    ) -> None:
        self._ai_client = ai_client
        self._audio_resolver = audio_resolver
        self._queue_service = queue_service
        self._session_repo = session_repository
        self._history_repo = history_repository
        self._settings = settings
        self._states: dict[DiscordSnowflake, RadioState] = {}

    # ── Public queries ────────────────────────────────────────────────

    def is_enabled(self, guild_id: DiscordSnowflake) -> bool:
        state = self._states.get(guild_id)
        return state is not None and state.enabled

    def get_state(self, guild_id: DiscordSnowflake) -> RadioState | None:
        """Return the guild's radio state (or None if no state exists)."""
        return self._states.get(guild_id)

    async def has_queued_tracks(self, guild_id: DiscordSnowflake) -> bool:
        """Check whether the guild's queue has any tracks waiting."""
        session = await self._session_repo.get(guild_id)
        return session is not None and session.queue_length > 0

    # ── Toggle / disable ──────────────────────────────────────────────

    async def toggle_radio(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        channel_id: DiscordSnowflake | None = None,
    ) -> RadioToggleResult:
        """Toggle radio on/off.

        When enabling: fetches batch_size recommendations, resolves visible_count
        for immediate playback, and stores the remainder in the pool.
        """
        if self.is_enabled(guild_id):
            self.disable_radio(guild_id)
            return RadioToggleResult(enabled=False, message="Radio disabled.")

        session = await self._session_repo.get(guild_id)
        if session is None or session.current_track is None:
            return RadioToggleResult(enabled=False, message="No track is currently playing.")

        if not await self._ai_client.is_available():
            return RadioToggleResult(enabled=False, message="AI service unavailable.")

        current_track = session.current_track

        # Create state with user/channel context for pool-exhaustion events
        state = RadioState(
            enabled=True,
            seed_track_title=current_track.title,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
        )
        self._states[guild_id] = state

        # Fetch a full batch from AI, seeded with recent session history
        exclude_ids = await self._collect_exclude_ids(guild_id)
        recent_tracks = await self._history_repo.get_recent(guild_id, limit=_SMART_SEED_LIMIT)
        recommendations = await self._fetch_recommendations(
            current_track,
            count=self._settings.batch_size,
            exclude_ids=exclude_ids,
            recent_tracks=recent_tracks,
        )

        if not recommendations:
            self.disable_radio(guild_id)
            return RadioToggleResult(
                enabled=False,
                message="Couldn't find similar tracks.",
            )

        # Split: resolve visible_count immediately, pool the rest
        visible_recs = recommendations[: self._settings.visible_count]
        pool_recs = recommendations[self._settings.visible_count :]

        enqueued = await self._resolve_and_enqueue_all(
            visible_recs,
            guild_id=guild_id,
            user_id=user_id,
            user_name=user_name,
        )

        if not enqueued:
            self.disable_radio(guild_id)
            return RadioToggleResult(
                enabled=False,
                message="Couldn't find similar tracks.",
            )

        # Store remaining unresolved recommendations in the pool
        state.pool = list(pool_recs)
        state.tracks_consumed += len(enqueued)

        logger.info(
            "Radio enabled in guild %s (seed='%s', queued=%d, pool=%d)",
            guild_id,
            current_track.title,
            len(enqueued),
            len(state.pool),
        )

        return RadioToggleResult(
            enabled=True,
            tracks_added=len(enqueued),
            generated_tracks=enqueued,
            seed_title=current_track.title,
        )

    def disable_radio(self, guild_id: DiscordSnowflake) -> None:
        had_state = guild_id in self._states
        self._states.pop(guild_id, None)
        if had_state:
            logger.info("Radio disabled in guild %s", guild_id)

    # ── Pool-based replenishment ──────────────────────────────────────

    async def replenish_from_pool(self, guild_id: DiscordSnowflake) -> int:
        """Pop one recommendation from the pool, resolve, and enqueue it.

        Called automatically when a track is consumed (played/skipped).
        Publishes RadioPoolExhausted when the pool runs dry.
        Returns the number of tracks added (0 or 1).
        """
        state = self._get_active_state(guild_id)
        if state is None:
            return 0

        if state.tracks_consumed >= self._settings.max_tracks_per_session:
            logger.info(
                "Radio session limit reached in guild %s (%d/%d tracks)",
                guild_id,
                state.tracks_consumed,
                self._settings.max_tracks_per_session,
            )
            self.disable_radio(guild_id)
            return 0

        if not state.pool:
            # Pool exhausted — publish event so the UI can prompt "Continue?"
            await self._publish_pool_exhausted(guild_id, state)
            return 0

        # Try recommendations from the pool until one resolves
        user_id = state.user_id or 0
        user_name = state.user_name or "Radio"

        while state.pool:
            rec = state.pool.pop(0)
            track = await self._try_resolve_and_enqueue(
                rec,
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )
            if track is not None:
                state.tracks_consumed += 1
                logger.debug(
                    "Radio pool: queued '%s' for guild %s (pool remaining=%d)",
                    track.title,
                    guild_id,
                    len(state.pool),
                )
                return 1

        # Exhausted pool trying to resolve — publish event
        await self._publish_pool_exhausted(guild_id, state)
        return 0

    async def continue_radio(self, guild_id: DiscordSnowflake) -> RadioToggleResult:
        """Continue radio after pool exhaustion — fetch a fresh batch.

        Called when the user accepts the "Continue?" prompt.
        """
        state = self._get_active_state(guild_id)
        if state is None:
            return RadioToggleResult(enabled=False, message="Radio is not active.")

        base_track = await self._get_base_track(guild_id)
        if base_track is None:
            return RadioToggleResult(enabled=False, message="No track is currently playing.")

        remaining_budget = self._settings.max_tracks_per_session - state.tracks_consumed
        if remaining_budget <= 0:
            self.disable_radio(guild_id)
            return RadioToggleResult(enabled=False, message="Radio session limit reached.")

        batch_size = min(self._settings.batch_size, remaining_budget)
        exclude_ids = await self._collect_exclude_ids(guild_id)
        recent_tracks = await self._history_repo.get_recent(guild_id, limit=_SMART_SEED_LIMIT)

        recommendations = await self._fetch_recommendations(
            base_track,
            count=batch_size,
            exclude_ids=exclude_ids,
            recent_tracks=recent_tracks,
        )

        if not recommendations:
            return RadioToggleResult(
                enabled=True,
                message="Couldn't find more similar tracks.",
            )

        # Split: resolve visible_count immediately, pool the rest
        visible_count = min(self._settings.visible_count, len(recommendations))
        visible_recs = recommendations[:visible_count]
        pool_recs = recommendations[visible_count:]

        user_id = state.user_id or 0
        user_name = state.user_name or "Radio"

        enqueued = await self._resolve_and_enqueue_all(
            visible_recs,
            guild_id=guild_id,
            user_id=user_id,
            user_name=user_name,
        )

        state.pool = list(pool_recs)
        state.tracks_consumed += len(enqueued)

        logger.info(
            "Radio continued in guild %s (queued=%d, pool=%d, total_consumed=%d)",
            guild_id,
            len(enqueued),
            len(state.pool),
            state.tracks_consumed,
        )

        return RadioToggleResult(
            enabled=True,
            tracks_added=len(enqueued),
            generated_tracks=enqueued,
            seed_title=state.seed_track_title,
            message="Radio continuing with fresh recommendations.",
        )

    # ── Reroll ────────────────────────────────────────────────────────

    async def reroll_track(
        self,
        guild_id: DiscordSnowflake,
        queue_position: int,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> Track | None:
        """Replace a single track at *queue_position* with a new recommendation."""
        state = self._get_active_state(guild_id)
        if state is None:
            return None

        base_track = await self._get_base_track(guild_id)
        if base_track is None:
            return None

        removed = await self._queue_service.remove(guild_id, queue_position)
        if removed is None:
            return None

        # Re-fetch after removal; include the removed track in exclusions
        exclude_ids = await self._collect_exclude_ids(guild_id, removed.id.value)

        recommendations = await self._fetch_recommendations(
            base_track,
            count=_REROLL_CANDIDATES,
            exclude_ids=exclude_ids,
        )
        if not recommendations:
            return None

        track = await self._resolve_and_enqueue_first(
            recommendations,
            guild_id=guild_id,
            user_id=user_id,
            user_name=user_name,
        )
        if track is None:
            return None

        # Move the newly enqueued track (at the end) to the original position
        new_session = await self._session_repo.get(guild_id)
        if new_session is not None and new_session.queue_length > 0:
            from_pos = new_session.queue_length - 1
            if from_pos != queue_position:
                await self._queue_service.move(guild_id, from_pos, queue_position)

        state.tracks_consumed += 1
        return track

    # ── Legacy refill / warmup (now pool-aware) ───────────────────────

    async def refill_queue(self, guild_id: DiscordSnowflake) -> int:
        """Refill the queue when exhausted — draws from pool first.

        If the pool is empty, publishes RadioPoolExhausted instead of
        calling AI directly (the user must accept "Continue?").
        """
        state = self._get_active_state(guild_id)
        if state is None:
            return 0

        if state.tracks_consumed >= self._settings.max_tracks_per_session:
            logger.info(
                "Radio session limit reached in guild %s (%d/%d tracks)",
                guild_id,
                state.tracks_consumed,
                self._settings.max_tracks_per_session,
            )
            self.disable_radio(guild_id)
            return 0

        logger.info("Radio refill triggered in guild %s", guild_id)

        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        remaining_capacity = session.MAX_QUEUE_SIZE - session.queue_length
        if remaining_capacity <= 0:
            return 0

        # Draw from pool up to visible_count or remaining capacity
        target = min(self._settings.visible_count, remaining_capacity)
        added = 0

        user_id = state.user_id or 0
        user_name = state.user_name or "Radio"

        for _ in range(target):
            if not state.pool:
                break
            rec = state.pool.pop(0)
            track = await self._try_resolve_and_enqueue(
                rec,
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )
            if track is not None:
                state.tracks_consumed += 1
                added += 1

        if added > 0:
            logger.info("Radio refill completed in guild %s: %d tracks from pool", guild_id, added)

        # If pool is now empty after refill, notify
        if not state.pool:
            await self._publish_pool_exhausted(guild_id, state)

        return added

    async def warmup_next(self, guild_id: DiscordSnowflake, *, recent_limit: int = 10) -> int:
        """Pre-fetch a single track from the pool so the queue is never empty.

        Draws from the pool instead of calling AI directly.
        """
        state = self._get_active_state(guild_id)
        if state is None:
            return 0

        if state.tracks_consumed >= self._settings.max_tracks_per_session:
            return 0

        session = await self._session_repo.get(guild_id)
        if session is None or session.queue_length > 0:
            return 0

        if not state.pool:
            await self._publish_pool_exhausted(guild_id, state)
            return 0

        user_id = state.user_id or 0
        user_name = state.user_name or "Radio"

        while state.pool:
            rec = state.pool.pop(0)
            track = await self._try_resolve_and_enqueue(
                rec,
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )
            if track is not None:
                state.tracks_consumed += 1
                logger.debug("Radio warmup: queued 1 track for guild %s", guild_id)
                return 1

        # Exhausted pool trying to resolve
        await self._publish_pool_exhausted(guild_id, state)
        return 0

    # ── Core pipeline ─────────────────────────────────────────────────

    async def _publish_pool_exhausted(
        self,
        guild_id: DiscordSnowflake,
        state: RadioState,
    ) -> None:
        """Publish RadioPoolExhausted so the UI layer can prompt the user."""
        logger.info(
            "Radio pool exhausted in guild %s (consumed=%d)",
            guild_id,
            state.tracks_consumed,
        )
        event = RadioPoolExhausted(
            guild_id=guild_id,
            channel_id=state.channel_id,
            tracks_generated=state.tracks_consumed,
        )
        await get_event_bus().publish(event)

    async def _try_resolve_and_enqueue(
        self,
        rec: Recommendation,
        *,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> Track | None:
        """Resolve a single recommendation and enqueue it. Returns the Track or None."""
        try:
            track = await self._audio_resolver.resolve(rec.query)
            if track is None:
                logger.warning("Radio: could not resolve '%s'", rec.query)
                return None

            track = track.model_copy(update={"is_from_recommendation": True})

            result = await self._queue_service.enqueue(
                guild_id=guild_id,
                track=track,
                user_id=user_id,
                user_name=user_name,
            )
            if result.success and result.track is not None:
                return result.track
            return None
        except Exception as exc:
            logger.warning("Radio: failed to resolve '%s': %s", rec.query, exc)
            return None

    # ── Shared helpers (no duplication) ───────────────────────────────

    def _get_active_state(self, guild_id: DiscordSnowflake) -> RadioState | None:
        """Return the guild's radio state if radio is active, else None."""
        state = self._states.get(guild_id)
        if state is None or not state.enabled:
            return None
        return state

    async def _get_base_track(self, guild_id: DiscordSnowflake) -> Track | None:
        """Return the currently playing track, or None."""
        session = await self._session_repo.get(guild_id)
        if session is None:
            return None
        return session.current_track

    @staticmethod
    def _session_exclude_ids(session: GuildPlaybackSession) -> list[str]:
        """Collect track IDs from the session's current track and queue."""
        ids: list[str] = []
        if session.current_track is not None:
            ids.append(session.current_track.id.value)
        for t in session.queue:
            ids.append(t.id.value)
        return ids

    async def _collect_exclude_ids(
        self, guild_id: DiscordSnowflake, *extra_ids: str,
    ) -> list[str]:
        """Build exclusion list from session state plus any extra IDs."""
        session = await self._session_repo.get(guild_id)
        ids = list(extra_ids)
        if session is not None:
            ids.extend(self._session_exclude_ids(session))
        return ids

    async def _fetch_recommendations(
        self,
        base_track: Track,
        *,
        count: int,
        exclude_ids: list[str],
        recent_tracks: list[Track] | None = None,
    ) -> list[Recommendation]:
        """Create recommendation request, call AI, and filter duplicates."""
        request = RecommendationRequest.from_track(
            base_track,
            count=count,
            exclude_ids=exclude_ids,
            recent_tracks=recent_tracks,
        )
        recommendations = await self._ai_client.get_recommendations(request)
        if not recommendations:
            return []
        return filter_duplicates(recommendations)

    async def _resolve_and_enqueue_first(
        self,
        recommendations: list[Recommendation],
        *,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> Track | None:
        """Resolve recommendations until one successfully enqueues. Returns that track."""
        for rec in recommendations:
            track = await self._try_resolve_and_enqueue(
                rec,
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )
            if track is not None:
                return track
        return None

    async def _resolve_and_enqueue_all(
        self,
        recommendations: list[Recommendation],
        *,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> list[Track]:
        """Resolve all recommendations and enqueue every success."""
        enqueued: list[Track] = []
        for rec in recommendations:
            track = await self._try_resolve_and_enqueue(
                rec,
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )
            if track is not None:
                enqueued.append(track)
        return enqueued
