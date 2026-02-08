"""Pause playback and prompt listeners when the track requester leaves voice."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...domain.shared.events import VoiceMemberLeftVoiceChannel, get_event_bus
from ...domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...application.interfaces.voice_adapter import VoiceAdapter
    from ...domain.music.entities import Track
    from ...domain.music.repository import SessionRepository
    from .playback_service import PlaybackApplicationService

logger = logging.getLogger(__name__)


class AutoSkipOnRequesterLeave:

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        playback_service: PlaybackApplicationService,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repo = session_repository
        self._playback_service = playback_service
        self._voice_adapter = voice_adapter
        self._bus = get_event_bus()
        self._guild_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._started = False
        self._on_requester_left_callback: Callable[[int, int, Track], Any] | None = None

    def set_on_requester_left_callback(self, callback: Callable[[int, int, Track], Any]) -> None:
        self._on_requester_left_callback = callback

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._started = False

    async def _on_member_left(self, event: VoiceMemberLeftVoiceChannel) -> None:
        lock = self._guild_locks[event.guild_id]
        async with lock:
            session = await self._session_repo.get(event.guild_id)
            if session is None or session.current_track is None:
                return

            current_track = session.current_track
            if current_track.requested_by_id is None:
                return

            if current_track.requested_by_id != event.user_id:
                return

            # If no listeners remain, skip immediately — no one to click buttons
            listeners = await self._voice_adapter.get_listeners(event.guild_id)
            if not listeners:
                logger.info(LogTemplates.REQUESTER_LEFT_NO_LISTENERS, event.guild_id)
                await self._playback_service.skip_track(event.guild_id)
                return

            # Pause playback and ask remaining listeners
            paused = await self._playback_service.pause_playback(event.guild_id)
            if not paused:
                return

            logger.info(
                LogTemplates.REQUESTER_LEFT_PAUSING,
                event.guild_id,
                event.user_id,
                current_track.id,
            )

            if self._on_requester_left_callback is not None:
                result = self._on_requester_left_callback(
                    event.guild_id, event.user_id, current_track
                )
                if asyncio.iscoroutine(result):
                    await result
