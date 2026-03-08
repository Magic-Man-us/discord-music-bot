"""AI-powered radio: manages per-guild state and orchestrates recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.music.entities import GuildPlaybackSession, Track
from ...domain.recommendations.entities import Recommendation, RecommendationRequest, filter_duplicates
from ...domain.shared.types import (
    DiscordSnowflake,
    NonEmptyStr,
    PositiveInt,
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


class RadioApplicationService:
    """Orchestrates the radio feature: AI recommendations -> resolve -> enqueue."""

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
    ) -> RadioToggleResult:
        """Toggle radio on/off, seeding from the currently playing track when enabling."""
        if self.is_enabled(guild_id):
            self.disable_radio(guild_id)
            return RadioToggleResult(enabled=False, message="Radio disabled.")

        session = await self._session_repo.get(guild_id)
        if session is None or session.current_track is None:
            return RadioToggleResult(enabled=False, message="No track is currently playing.")

        if not await self._ai_client.is_available():
            return RadioToggleResult(enabled=False, message="AI service unavailable.")

        current_track = session.current_track

        state = RadioState(enabled=True, seed_track_title=current_track.title)
        self._states[guild_id] = state

        tracks = await self._generate_and_enqueue(
            guild_id=guild_id,
            base_track=current_track,
            user_id=user_id,
            user_name=user_name,
            count=self._settings.default_count,
        )

        if not tracks:
            self.disable_radio(guild_id)
            return RadioToggleResult(
                enabled=False,
                message="Couldn't find similar tracks.",
            )

        logger.info("Radio enabled in guild %s (seed='%s')", guild_id, current_track.title)
        return RadioToggleResult(
            enabled=True,
            tracks_added=len(tracks),
            generated_tracks=tracks,
            seed_title=current_track.title,
        )

    def disable_radio(self, guild_id: DiscordSnowflake) -> None:
        had_state = guild_id in self._states
        self._states.pop(guild_id, None)
        if had_state:
            logger.info("Radio disabled in guild %s", guild_id)

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
            base_track, count=_REROLL_CANDIDATES, exclude_ids=exclude_ids,
        )
        if not recommendations:
            return None

        track = await self._resolve_and_enqueue_first(
            recommendations, guild_id=guild_id, user_id=user_id, user_name=user_name,
        )
        if track is None:
            return None

        # Move the newly enqueued track (at the end) to the original position
        new_session = await self._session_repo.get(guild_id)
        if new_session is not None and new_session.queue_length > 0:
            from_pos = new_session.queue_length - 1
            if from_pos != queue_position:
                await self._queue_service.move(guild_id, from_pos, queue_position)

        state.tracks_generated += 1
        return track

    # ── Refill / warmup ──────────────────────────────────────────────

    async def refill_queue(self, guild_id: DiscordSnowflake) -> int:
        """Refill the queue with more radio tracks when the queue is exhausted."""
        state = self._get_active_state(guild_id)
        if state is None:
            return 0

        if state.tracks_generated >= self._settings.max_tracks_per_session:
            logger.info(
                "Radio session limit reached in guild %s (%d/%d tracks)",
                guild_id,
                state.tracks_generated,
                self._settings.max_tracks_per_session,
            )
            self.disable_radio(guild_id)
            return 0

        logger.info("Radio refill triggered in guild %s", guild_id)

        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        base_track = session.current_track
        if base_track is None:
            return 0

        remaining_budget = self._settings.max_tracks_per_session - state.tracks_generated
        count = min(self._settings.default_count, remaining_budget)

        remaining_capacity = session.MAX_QUEUE_SIZE - session.queue_length
        if remaining_capacity <= 0:
            return 0
        count = min(count, remaining_capacity)

        try:
            tracks = await self._generate_and_enqueue(
                guild_id=guild_id,
                base_track=base_track,
                user_id=base_track.requested_by_id or 0,
                user_name=base_track.requested_by_name or "Radio",
                count=count,
            )
            added = len(tracks)
            logger.info("Radio refill completed in guild %s: %d tracks added", guild_id, added)
            return added
        except Exception as exc:
            logger.exception("Radio refill failed in guild %s: %s", guild_id, exc)
            return 0

    async def warmup_next(self, guild_id: DiscordSnowflake, *, recent_limit: int = 10) -> int:
        """Pre-fetch a single track so the queue is never empty while radio is active.

        Excludes the current track, any queued tracks, and the last *recent_limit*
        tracks from history to avoid immediate repeats.
        """
        state = self._get_active_state(guild_id)
        if state is None:
            return 0

        if state.tracks_generated >= self._settings.max_tracks_per_session:
            return 0

        session = await self._session_repo.get(guild_id)
        if session is None or session.queue_length > 0:
            return 0

        base_track = session.current_track
        if base_track is None:
            return 0

        # Build exclusion set: current + queued + recent history
        exclude_ids = self._session_exclude_ids(session)
        recent = await self._history_repo.get_recent(guild_id, limit=recent_limit)
        for t in recent:
            if t.id.value not in exclude_ids:
                exclude_ids.append(t.id.value)

        recommendations = await self._fetch_recommendations(
            base_track, count=1, exclude_ids=exclude_ids,
        )
        if not recommendations:
            return 0

        track = await self._resolve_and_enqueue_first(
            recommendations,
            guild_id=guild_id,
            user_id=base_track.requested_by_id or 0,
            user_name=base_track.requested_by_name or "Radio",
        )
        if track is None:
            return 0

        state.tracks_generated += 1
        logger.debug("Radio warmup: queued 1 track for guild %s", guild_id)
        return 1

    # ── Core pipeline ─────────────────────────────────────────────────

    async def _generate_and_enqueue(
        self,
        *,
        guild_id: DiscordSnowflake,
        base_track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        count: PositiveInt,
    ) -> list[Track]:
        """Generate recommendations and enqueue all resolved tracks."""
        exclude_ids = await self._collect_exclude_ids(guild_id)

        recommendations = await self._fetch_recommendations(
            base_track, count=count, exclude_ids=exclude_ids,
        )
        if not recommendations:
            return []

        enqueued = await self._resolve_and_enqueue_all(
            recommendations, guild_id=guild_id, user_id=user_id, user_name=user_name,
        )

        state = self._states.get(guild_id)
        if state is not None:
            state.tracks_generated += len(enqueued)

        return enqueued

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
    ) -> list[Recommendation]:
        """Create recommendation request, call AI, and filter duplicates."""
        request = RecommendationRequest.from_track(
            base_track,
            count=count,
            exclude_ids=exclude_ids,
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
            try:
                track = await self._audio_resolver.resolve(rec.query)
                if track is None:
                    logger.warning("Radio: could not resolve '%s'", rec.query)
                    continue

                result = await self._queue_service.enqueue(
                    guild_id=guild_id,
                    track=track,
                    user_id=user_id,
                    user_name=user_name,
                )
                if result.success and result.track is not None:
                    return result.track
            except Exception as exc:
                logger.warning("Radio: failed to resolve '%s': %s", rec.query, exc)
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
            try:
                track = await self._audio_resolver.resolve(rec.query)
                if track is None:
                    logger.warning("Radio: could not resolve '%s'", rec.query)
                    continue

                result = await self._queue_service.enqueue(
                    guild_id=guild_id,
                    track=track,
                    user_id=user_id,
                    user_name=user_name,
                )
                if result.success and result.track is not None:
                    enqueued.append(result.track)
            except Exception as exc:
                logger.warning("Radio: failed to resolve '%s': %s", rec.query, exc)
        return enqueued
