"""Radio Application Service — AI-powered similar song discovery.

Manages per-guild radio state and orchestrates AI recommendations,
track resolution, and queue filling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...domain.music.entities import Track
from ...domain.recommendations.services import RecommendationDomainService
from ...domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...config.settings import RadioSettings
    from ...domain.music.repository import SessionRepository
    from ..interfaces.ai_client import AIClient
    from ..interfaces.audio_resolver import AudioResolver
    from .queue_service import QueueApplicationService

logger = logging.getLogger(__name__)


@dataclass
class _RadioState:
    """In-memory radio state for a single guild."""

    enabled: bool = False
    seed_track_title: str = ""
    tracks_generated: int = 0


@dataclass
class RadioToggleResult:
    """Result of a radio toggle operation."""

    enabled: bool
    tracks_added: int = 0
    seed_title: str = ""
    message: str = ""


class RadioApplicationService:
    """Orchestrates the radio feature: AI recommendations -> resolve -> enqueue."""

    def __init__(
        self,
        *,
        ai_client: AIClient,
        audio_resolver: AudioResolver,
        queue_service: QueueApplicationService,
        session_repository: SessionRepository,
        settings: RadioSettings,
    ) -> None:
        self._ai_client = ai_client
        self._audio_resolver = audio_resolver
        self._queue_service = queue_service
        self._session_repo = session_repository
        self._settings = settings
        self._states: dict[int, _RadioState] = {}

    def is_enabled(self, guild_id: int) -> bool:
        """Check whether radio is currently enabled for a guild."""
        state = self._states.get(guild_id)
        return state is not None and state.enabled

    async def toggle_radio(
        self,
        guild_id: int,
        user_id: int,
        user_name: str,
    ) -> RadioToggleResult:
        """Toggle radio on/off for a guild.

        When enabling, generates and enqueues the first batch of recommendations
        based on the currently playing track.
        """
        if self.is_enabled(guild_id):
            self.disable_radio(guild_id)
            return RadioToggleResult(enabled=False, message="Radio disabled.")

        # Get the currently playing track
        session = await self._session_repo.get(guild_id)
        if session is None or session.current_track is None:
            return RadioToggleResult(enabled=False, message="No track is currently playing.")

        # Check AI availability
        if not await self._ai_client.is_available():
            return RadioToggleResult(enabled=False, message="AI service unavailable.")

        current_track = session.current_track

        # Enable radio
        state = _RadioState(enabled=True, seed_track_title=current_track.title)
        self._states[guild_id] = state

        # Generate first batch
        added = await self._generate_and_enqueue(
            guild_id=guild_id,
            base_track=current_track,
            user_id=user_id,
            user_name=user_name,
            count=self._settings.default_count,
        )

        if added == 0:
            # Failed to add any tracks — disable radio
            self.disable_radio(guild_id)
            return RadioToggleResult(
                enabled=False,
                message="Couldn't find similar tracks.",
            )

        logger.info(LogTemplates.RADIO_ENABLED, guild_id, current_track.title)
        return RadioToggleResult(
            enabled=True,
            tracks_added=added,
            seed_title=current_track.title,
        )

    def disable_radio(self, guild_id: int) -> None:
        """Disable radio for a guild and clean up state."""
        had_state = guild_id in self._states
        self._states.pop(guild_id, None)
        if had_state:
            logger.info(LogTemplates.RADIO_DISABLED, guild_id)

    async def refill_queue(self, guild_id: int) -> int:
        """Refill the queue with more radio tracks.

        Called by the auto-refill subscriber when the queue is exhausted.

        Returns:
            Number of tracks added.
        """
        state = self._states.get(guild_id)
        if state is None or not state.enabled:
            return 0

        # Check session limit
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

        # Get the last played track as seed for next batch
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        # Use current track or fall back to seed title
        base_track = session.current_track
        if base_track is None:
            return 0

        remaining_budget = self._settings.max_tracks_per_session - state.tracks_generated
        count = min(self._settings.default_count, remaining_budget)

        # Respect queue capacity
        remaining_capacity = session.MAX_QUEUE_SIZE - session.queue_length
        if remaining_capacity <= 0:
            return 0
        count = min(count, remaining_capacity)

        try:
            added = await self._generate_and_enqueue(
                guild_id=guild_id,
                base_track=base_track,
                user_id=base_track.requested_by_id or 0,
                user_name=base_track.requested_by_name or "Radio",
                count=count,
            )
            logger.info(LogTemplates.RADIO_REFILL_COMPLETED, guild_id, added)
            return added
        except Exception as exc:
            logger.exception(LogTemplates.RADIO_REFILL_FAILED, guild_id, exc)
            return 0

    async def _generate_and_enqueue(
        self,
        *,
        guild_id: int,
        base_track: Track,
        user_id: int,
        user_name: str,
        count: int,
    ) -> int:
        """Generate recommendations and enqueue resolved tracks.

        Returns:
            Number of tracks successfully enqueued.
        """
        # Build exclude list from current queue + current track
        session = await self._session_repo.get(guild_id)
        exclude_ids: list[str] = []
        if session is not None:
            if session.current_track is not None:
                exclude_ids.append(session.current_track.id.value)
            for t in session.queue:
                exclude_ids.append(t.id.value)

        # Create recommendation request
        request = RecommendationDomainService.create_request_from_track(
            track=base_track,
            count=count,
            exclude_ids=exclude_ids,
        )

        # Get AI recommendations
        recommendations = await self._ai_client.get_recommendations(request)
        if not recommendations:
            return 0

        # Deduplicate
        recommendations = RecommendationDomainService.filter_duplicates(recommendations)

        # Resolve and enqueue each recommendation
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
                    user_id=user_id,
                    user_name=user_name,
                )
                if result.success:
                    added += 1
            except Exception as exc:
                logger.warning(LogTemplates.RADIO_TRACK_RESOLVE_FAILED, rec.query, str(exc))
                continue

        # Update state
        state = self._states.get(guild_id)
        if state is not None:
            state.tracks_generated += added

        return added
