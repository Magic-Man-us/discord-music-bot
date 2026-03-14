"""Auto-DJ: automatically starts radio when the queue empties and no one adds tracks.

Subscribes to QueueExhausted → waits AUTO_DJ_DELAY_SECONDS → if still idle and
radio is not already active, toggles radio on using the last played track as seed.
Cancels the timer when a new track starts (TrackStartedPlaying).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ...domain.shared.constants import TimeConstants
from ...domain.shared.events import QueueExhausted, TrackStartedPlaying, get_event_bus
from ...domain.shared.types import DiscordSnowflake

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository, TrackHistoryRepository
    from ..interfaces.ai_client import AIClient
    from .playback_service import PlaybackApplicationService
    from .radio_service import RadioApplicationService

logger = logging.getLogger(__name__)


class AutoDJ:
    """Subscribes to queue exhaustion and auto-enables radio after a delay.

    Only activates when:
    - AI is available
    - Radio is not already active for the guild
    - The guild still has no queued tracks after the delay
    - There is play history to seed from
    """

    def __init__(
        self,
        *,
        radio_service: RadioApplicationService,
        playback_service: PlaybackApplicationService,
        session_repository: SessionRepository,
        history_repository: TrackHistoryRepository,
        ai_client: AIClient,
    ) -> None:
        self._radio_service = radio_service
        self._playback_service = playback_service
        self._session_repo = session_repository
        self._history_repo = history_repository
        self._ai_client = ai_client
        self._bus = get_event_bus()
        self._started = False
        self._timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(QueueExhausted, self._on_queue_exhausted)
        self._bus.subscribe(TrackStartedPlaying, self._on_track_started)
        self._started = True
        logger.info("Auto-DJ started")

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(QueueExhausted, self._on_queue_exhausted)
        self._bus.unsubscribe(TrackStartedPlaying, self._on_track_started)
        for timer in self._timers.values():
            if not timer.done():
                timer.cancel()
        self._timers.clear()
        self._started = False

    async def _on_queue_exhausted(self, event: QueueExhausted) -> None:
        """Schedule auto-DJ activation after a delay."""
        guild_id = event.guild_id

        # Don't schedule if radio is already active
        if self._radio_service.is_enabled(guild_id):
            return

        self._cancel_timer(guild_id)
        delay = TimeConstants.AUTO_DJ_DELAY_SECONDS
        if delay <= 0:
            return

        logger.debug(
            "Queue exhausted in guild %s, scheduling auto-DJ in %ss",
            guild_id,
            delay,
        )
        self._timers[guild_id] = asyncio.create_task(
            self._delayed_activate(guild_id, delay)
        )

    async def _on_track_started(self, event: TrackStartedPlaying) -> None:
        """Cancel any pending auto-DJ timer when a track starts."""
        self._cancel_timer(event.guild_id)

    def _cancel_timer(self, guild_id: DiscordSnowflake) -> None:
        timer = self._timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()

    async def _delayed_activate(self, guild_id: DiscordSnowflake, delay: int) -> None:
        """Wait, then activate radio if conditions are still met."""
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        # Re-check conditions after delay
        if self._radio_service.is_enabled(guild_id):
            return

        session = await self._session_repo.get(guild_id)
        if session is None:
            return

        # Don't activate if someone added tracks during the delay
        if session.has_tracks:
            return

        if not await self._ai_client.is_available():
            return

        # Need a seed track — use most recent from history
        recent = await self._history_repo.get_recent(guild_id, limit=1)
        if not recent:
            logger.debug("Auto-DJ: no history to seed from in guild %s", guild_id)
            return

        # Use the last track's requester info, or defaults
        last_track = recent[0]
        user_id = last_track.requested_by_id or 0
        user_name = last_track.requested_by_name or "Auto-DJ"

        logger.info(
            "Auto-DJ activating in guild %s (seed='%s')",
            guild_id,
            last_track.title,
        )

        injected_seed = session.current_track is None
        try:
            if injected_seed:
                session.set_current_track(last_track)
                await self._session_repo.save(session)

            result = await self._radio_service.toggle_radio(
                guild_id=guild_id,
                user_id=user_id,
                user_name=user_name,
            )

            if result.enabled and result.tracks_added > 0:
                logger.info("Auto-DJ enabled in guild %s: %d tracks queued", guild_id, result.tracks_added)
                await self._playback_service.start_playback(guild_id)
            else:
                logger.debug("Auto-DJ could not enable radio in guild %s: %s", guild_id, result.message)
        except Exception:
            logger.exception("Auto-DJ failed for guild %s", guild_id)
        finally:
            if injected_seed:
                await self._clear_injected_seed(guild_id)

    async def _clear_injected_seed(self, guild_id: DiscordSnowflake) -> None:
        session = await self._session_repo.get(guild_id)
        if session is not None and session.current_track is not None:
            session.set_current_track(None)
            await self._session_repo.save(session)
