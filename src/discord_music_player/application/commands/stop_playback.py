"""Command and handler for stopping playback and clearing the queue."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ..interfaces.voice_adapter import VoiceAdapter


class StopStatus(Enum):
    """Status codes for stop results."""

    SUCCESS = "success"
    NOTHING_PLAYING = "nothing_playing"
    NOT_IN_CHANNEL = "not_in_channel"
    ERROR = "error"


@dataclass
class StopPlaybackCommand:

    guild_id: int
    user_id: int
    clear_queue: bool = True
    disconnect: bool = False

    def __post_init__(self) -> None:
        if self.guild_id <= 0:
            raise ValueError("Guild ID must be positive")
        if self.user_id <= 0:
            raise ValueError("User ID must be positive")


@dataclass
class StopResult:

    status: StopStatus
    message: str
    tracks_cleared: int = 0
    disconnected: bool = False

    @property
    def is_success(self) -> bool:
        return self.status == StopStatus.SUCCESS

    @classmethod
    def success(cls, tracks_cleared: int = 0, disconnected: bool = False) -> StopResult:
        if disconnected:
            message = "Stopped playback and disconnected."
        elif tracks_cleared > 0:
            message = f"Stopped playback and cleared {tracks_cleared} tracks from queue."
        else:
            message = "Stopped playback."

        return cls(
            status=StopStatus.SUCCESS,
            message=message,
            tracks_cleared=tracks_cleared,
            disconnected=disconnected,
        )

    @classmethod
    def error(cls, status: StopStatus, message: str) -> StopResult:
        return cls(status=status, message=message)


class StopPlaybackHandler:

    def __init__(
        self,
        session_repository: SessionRepository,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repo = session_repository
        self._voice_adapter = voice_adapter

    async def handle(self, command: StopPlaybackCommand) -> StopResult:
        session = await self._session_repo.get(command.guild_id)

        if session is None:
            return StopResult.error(StopStatus.NOTHING_PLAYING, "Nothing is currently playing")

        await self._voice_adapter.stop(command.guild_id)

        tracks_cleared = 0
        if command.clear_queue:
            tracks_cleared = session.clear_queue()

        session.stop()

        disconnected = False
        if command.disconnect:
            disconnected = await self._voice_adapter.disconnect(command.guild_id)
            await self._session_repo.delete(command.guild_id)
        else:
            await self._session_repo.save(session)

        return StopResult.success(tracks_cleared, disconnected)
