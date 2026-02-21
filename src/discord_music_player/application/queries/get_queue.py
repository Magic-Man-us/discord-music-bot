"""Query for retrieving the current queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.shared.types import DiscordSnowflake, NonNegativeInt

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository


class GetQueueQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    guild_id: DiscordSnowflake


class QueueInfo(BaseModel):

    guild_id: DiscordSnowflake
    tracks: list[Track] = Field(default_factory=list)
    current_track: Track | None = None
    total_duration: NonNegativeInt | None = None

    @property
    def length(self) -> int:
        return len(self.tracks)

    @property
    def is_empty(self) -> bool:
        return len(self.tracks) == 0


class GetQueueHandler:

    def __init__(self, *, session_repository: SessionRepository) -> None:
        self._session_repo = session_repository

    async def handle(self, query: GetQueueQuery) -> QueueInfo:
        session = await self._session_repo.get(query.guild_id)

        if session is None:
            return QueueInfo(
                guild_id=query.guild_id,
                tracks=[],
                current_track=None,
                total_duration=0,
            )

        total_duration = sum(
            t.duration_seconds for t in session.queue if t.duration_seconds is not None
        )

        return QueueInfo(
            guild_id=query.guild_id,
            tracks=list(session.queue),
            current_track=session.current_track,
            total_duration=total_duration,
        )
