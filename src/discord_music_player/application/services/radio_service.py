"""AI-powered radio: manages per-guild state and orchestrates recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.music.entities import Track
from ...domain.recommendations.services import RecommendationDomainService
from ...domain.shared.messages import LogTemplates
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

    def is_enabled(self, guild_id: DiscordSnowflake) -> bool:
        state = self._states.get(guild_id)
        return state is not None and state.enabled

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

        logger.info(LogTemplates.RADIO_ENABLED, guild_id, current_track.title)
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
            logger.info(LogTemplates.RADIO_DISABLED, guild_id)

    async def reroll_track(
        self,
        guild_id: DiscordSnowflake,
        queue_position: int,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> Track | None:
        """Replace a single track at *queue_position* with a new recommendation.

        Returns the newly enqueued Track, or None on failure.
        """
        state = self._states.get(guild_id)
        if state is None or not state.enabled:
            return None

        session = await self._session_repo.get(guild_id)
        if session is None:
            return None

        base_track = session.current_track
        if base_track is None:
            return None

        # Remove the old track
        removed = await self._queue_service.remove(guild_id, queue_position)
        if removed is None:
            return None

        # Build exclusion set: current + all remaining queued + the removed track
        session = await self._session_repo.get(guild_id)  # re-fetch after removal
        exclude_ids: list[str] = [removed.id.value]
        if session is not None:
            if session.current_track is not None:
                exclude_ids.append(session.current_track.id.value)
            for t in session.queue:
                exclude_ids.append(t.id.value)

        request = RecommendationDomainService.create_request_from_track(
            track=base_track,
            count=1,
            exclude_ids=exclude_ids,
        )

        recommendations = await self._ai_client.get_recommendations(request)
        if not recommendations:
            return None

        recommendations = RecommendationDomainService.filter_duplicates(recommendations)

        for rec in recommendations:
            try:
                track = await self._audio_resolver.resolve(rec.query)
                if track is None:
                    continue

                result = await self._queue_service.enqueue(
                    guild_id=guild_id,
                    track=track,
                    user_id=user_id,
                    user_name=user_name,
                )
                if result.success and result.track is not None:
                    # Move the newly enqueued track (at the end) to the original position
                    new_session = await self._session_repo.get(guild_id)
                    if new_session is not None and new_session.queue_length > 0:
                        from_pos = new_session.queue_length - 1
                        if from_pos != queue_position:
                            await self._queue_service.move(guild_id, from_pos, queue_position)

                    if state is not None:
                        state.tracks_generated += 1

                    return result.track
            except Exception as exc:
                logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, str(exc))
                continue

        return None

    async def refill_queue(self, guild_id: DiscordSnowflake) -> int:
        """Refill the queue with more radio tracks when the queue is exhausted."""
        state = self._states.get(guild_id)
        if state is None or not state.enabled:
            return 0

        if state.tracks_generated >= self._settings.max_tracks_per_session:
            logger.info(
                LogTemplates.RADIO_SESSION_LIMIT,
                guild_id,
                state.tracks_generated,
                self._settings.max_tracks_per_session,
            )
            self.disable_radio(guild_id)
            return 0

        logger.info(LogTemplates.RADIO_REFILL_TRIGGERED, guild_id)

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
            logger.info(LogTemplates.RADIO_REFILL_COMPLETED, guild_id, added)
            return added
        except Exception as exc:
            logger.exception(LogTemplates.RADIO_REFILL_FAILED, guild_id, exc)
            return 0

    async def warmup_next(self, guild_id: DiscordSnowflake, *, recent_limit: int = 10) -> int:
        """Pre-fetch a single track so the queue is never empty while radio is active.

        Excludes the current track, any queued tracks, and the last *recent_limit*
        tracks from history to avoid immediate repeats.
        """
        state = self._states.get(guild_id)
        if state is None or not state.enabled:
            return 0

        if state.tracks_generated >= self._settings.max_tracks_per_session:
            return 0

        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        # Only warm up when the queue is empty
        if session.queue_length > 0:
            return 0

        base_track = session.current_track
        if base_track is None:
            return 0

        # Build exclusion set: current + queued + recent history
        exclude_ids: list[str] = [base_track.id.value]
        for t in session.queue:
            exclude_ids.append(t.id.value)

        recent = await self._history_repo.get_recent(guild_id, limit=recent_limit)
        for t in recent:
            if t.id.value not in exclude_ids:
                exclude_ids.append(t.id.value)

        request = RecommendationDomainService.create_request_from_track(
            track=base_track,
            count=1,
            exclude_ids=exclude_ids,
        )

        recommendations = await self._ai_client.get_recommendations(request)
        if not recommendations:
            return 0

        recommendations = RecommendationDomainService.filter_duplicates(recommendations)

        added = 0
        for rec in recommendations:
            try:
                track = await self._audio_resolver.resolve(rec.query)
                if track is None:
                    logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, "no result")
                    continue

                result = await self._queue_service.enqueue(
                    guild_id=guild_id,
                    track=track,
                    user_id=base_track.requested_by_id or 0,
                    user_name=base_track.requested_by_name or "Radio",
                )
                if result.success:
                    added += 1
                    break  # Only need one track for warmup
            except Exception as exc:
                logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, str(exc))
                continue

        if state is not None and added > 0:
            state.tracks_generated += added
            logger.debug("Radio warmup: queued 1 track for guild %s", guild_id)

        return added

    async def _generate_and_enqueue(
        self,
        *,
        guild_id: DiscordSnowflake,
        base_track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        count: PositiveInt,
    ) -> list[Track]:
        """Generate recommendations and enqueue resolved tracks.

        Returns the list of successfully enqueued Track objects.
        """
        session = await self._session_repo.get(guild_id)
        exclude_ids: list[str] = []
        if session is not None:
            if session.current_track is not None:
                exclude_ids.append(session.current_track.id.value)
            for t in session.queue:
                exclude_ids.append(t.id.value)

        request = RecommendationDomainService.create_request_from_track(
            track=base_track,
            count=count,
            exclude_ids=exclude_ids,
        )

        recommendations = await self._ai_client.get_recommendations(request)
        if not recommendations:
            return []

        recommendations = RecommendationDomainService.filter_duplicates(recommendations)

        enqueued_tracks: list[Track] = []
        for rec in recommendations:
            try:
                track = await self._audio_resolver.resolve(rec.query)
                if track is None:
                    logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, "no result")
                    continue

                result = await self._queue_service.enqueue(
                    guild_id=guild_id,
                    track=track,
                    user_id=user_id,
                    user_name=user_name,
                )
                if result.success and result.track is not None:
                    enqueued_tracks.append(result.track)
            except Exception as exc:
                logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, str(exc))
                continue

        state = self._states.get(guild_id)
        if state is not None:
            state.tracks_generated += len(enqueued_tracks)

        return enqueued_tracks
