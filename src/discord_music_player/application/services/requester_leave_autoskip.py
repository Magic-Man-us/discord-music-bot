"""Pause playback and prompt listeners when the track requester leaves voice."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...domain.shared.events import (
    VoiceMemberJoinedVoiceChannel,
    VoiceMemberLeftVoiceChannel,
    get_event_bus,
)
from ...domain.shared.types import DiscordSnowflake
from ...utils.logging import get_logger

if TYPE_CHECKING:
    from ...application.interfaces.voice_adapter import VoiceAdapter
    from ...domain.music.entities import Track
    from ...domain.music.repository import SessionRepository
    from .playback_service import PlaybackApplicationService

logger = get_logger(__name__)


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
        self._guild_locks: dict[DiscordSnowflake, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._started = False

        # guild_id → user_id of the requester who left (pending prompt)
        self._pending_requester: dict[DiscordSnowflake, DiscordSnowflake] = {}

        self._on_requester_left_callback: (
            Callable[[DiscordSnowflake, DiscordSnowflake, Track], Any] | None
        ) = None
        self._on_requester_rejoined_callback: (
            Callable[[DiscordSnowflake, DiscordSnowflake], Any] | None
        ) = None

    def set_on_requester_left_callback(
        self, callback: Callable[[DiscordSnowflake, DiscordSnowflake, Track], Any] | None
    ) -> None:
        self._on_requester_left_callback = callback

    def set_on_requester_rejoined_callback(
        self, callback: Callable[[DiscordSnowflake, DiscordSnowflake], Any] | None
    ) -> None:
        self._on_requester_rejoined_callback = callback

    def clear_pending(self, guild_id: DiscordSnowflake) -> None:
        """Clear the pending requester-left state (called when the view resolves)."""
        self._pending_requester.pop(guild_id, None)

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._bus.subscribe(VoiceMemberJoinedVoiceChannel, self._on_member_joined)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._bus.unsubscribe(VoiceMemberJoinedVoiceChannel, self._on_member_joined)
        self._started = False
        self._pending_requester.clear()
        self._guild_locks.clear()

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
                logger.info(
                    "Requester left voice channel in guild %s, no listeners remain — auto-skipping",
                    event.guild_id,
                )
                await self._playback_service.skip_track(event.guild_id)
                return

            # Pause playback and ask remaining listeners
            paused = await self._playback_service.pause_playback(event.guild_id)
            if not paused:
                return

            logger.info(
                "Requester left voice channel in guild %s (user_id=%s, track_id=%s), pausing playback",
                event.guild_id,
                event.user_id,
                current_track.id,
            )

            self._pending_requester[event.guild_id] = event.user_id

            if self._on_requester_left_callback is not None:
                result = self._on_requester_left_callback(
                    event.guild_id, event.user_id, current_track
                )
                if asyncio.iscoroutine(result):
                    await result

    async def _on_member_joined(self, event: VoiceMemberJoinedVoiceChannel) -> None:
        lock = self._guild_locks[event.guild_id]
        async with lock:
            pending_user = self._pending_requester.pop(event.guild_id, None)
            if pending_user is None or pending_user != event.user_id:
                if pending_user is not None:
                    self._pending_requester[event.guild_id] = pending_user
                return

            logger.info(
                "Requester %s rejoined voice in guild %s — auto-resuming playback",
                event.user_id,
                event.guild_id,
            )
            await self._playback_service.resume_playback(event.guild_id)

            if self._on_requester_rejoined_callback is not None:
                result = self._on_requester_rejoined_callback(event.guild_id, event.user_id)
                if asyncio.iscoroutine(result):
                    await result
