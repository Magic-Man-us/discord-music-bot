"""Auto-skip the current track when its requester leaves the voice channel."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import TYPE_CHECKING

from ...domain.shared.events import VoiceMemberLeftVoiceChannel, get_event_bus

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from .playback_service import PlaybackApplicationService

logger = logging.getLogger(__name__)


class AutoSkipOnRequesterLeave:

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        playback_service: PlaybackApplicationService,
    ) -> None:
        self._session_repo = session_repository
        self._playback_service = playback_service
        self._bus = get_event_bus()
        self._guild_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._started = False

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

            skipped = await self._playback_service.skip_track(event.guild_id)
            if skipped is None:
                return

            logger.info(
                "Auto-skipped requester track in guild %s (user_id=%s, track_id=%s)",
                event.guild_id,
                event.user_id,
                skipped.id,
            )
