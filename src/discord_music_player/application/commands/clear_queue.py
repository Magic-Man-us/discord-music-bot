"""Command and handler for clearing the queue."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.shared.types import DiscordSnowflake, NonNegativeInt

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository


class ClearStatus(Enum):
    """Status codes for clear queue results."""

    SUCCESS = "success"
    QUEUE_EMPTY = "queue_empty"
    NOT_IN_CHANNEL = "not_in_channel"
    ERROR = "error"


class ClearQueueCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    guild_id: DiscordSnowflake
    user_id: DiscordSnowflake


class ClearResult(BaseModel):

    status: ClearStatus
    message: str
    tracks_cleared: NonNegativeInt = 0

    @property
    def is_success(self) -> bool:
        return self.status == ClearStatus.SUCCESS

    @classmethod
    def success(cls, tracks_cleared: int) -> ClearResult:
        return cls(
            status=ClearStatus.SUCCESS,
            message=f"Cleared {tracks_cleared} tracks from the queue.",
            tracks_cleared=tracks_cleared,
        )

    @classmethod
    def error(cls, status: ClearStatus, message: str) -> ClearResult:
        return cls(status=status, message=message)


class ClearQueueHandler:

    def __init__(self, *, session_repository: SessionRepository) -> None:
        self._session_repo = session_repository

    async def handle(self, command: ClearQueueCommand) -> ClearResult:
        session = await self._session_repo.get(command.guild_id)

        if session is None or session.queue_length == 0:
            return ClearResult.error(ClearStatus.QUEUE_EMPTY, "Queue is already empty")

        tracks_cleared = session.clear_queue()
        await self._session_repo.save(session)

        return ClearResult.success(tracks_cleared)
