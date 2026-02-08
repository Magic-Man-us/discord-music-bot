"""
Get Current Track Query

Query for retrieving the currently playing track.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.entities import Track
    from ...domain.music.repository import SessionRepository


@dataclass
class GetCurrentTrackQuery:
    """Query to get the current track for a guild."""

    guild_id: int


@dataclass
class CurrentTrackInfo:
    """Result containing current track information."""

    guild_id: int
    track: Track | None
    is_playing: bool
    is_paused: bool
    queue_length: int


class GetCurrentTrackHandler:
    """Handler for GetCurrentTrackQuery."""

    def __init__(self, session_repository: SessionRepository) -> None:
        self._session_repository = session_repository

    async def handle(self, query: GetCurrentTrackQuery) -> CurrentTrackInfo:
        session = await self._session_repository.get(query.guild_id)

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
