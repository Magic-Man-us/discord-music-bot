"""Query for retrieving the currently playing track."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.shared.types import DiscordSnowflake, NonNegativeInt

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository


class GetCurrentTrackQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    guild_id: DiscordSnowflake


class CurrentTrackInfo(BaseModel):

    guild_id: DiscordSnowflake
    track: Track | None = None
    is_playing: bool = False
    is_paused: bool = False
    queue_length: NonNegativeInt = 0


class GetCurrentTrackHandler:

    def __init__(self, *, session_repository: SessionRepository) -> None:
        self._session_repo = session_repository

    async def handle(self, query: GetCurrentTrackQuery) -> CurrentTrackInfo:
        session = await self._session_repo.get(query.guild_id)

        if session is None:
            return CurrentTrackInfo(
                guild_id=query.guild_id,
                track=None,
                is_playing=False,
                is_paused=False,
                queue_length=0,
            )

        return CurrentTrackInfo(
            guild_id=query.guild_id,
            track=session.current_track,
            is_playing=session.is_playing,
            is_paused=session.is_paused,
            queue_length=session.queue_length,
        )
