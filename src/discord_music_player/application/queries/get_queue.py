"""
Get Queue Query

Query for retrieving the current queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.entities import Track
    from ...domain.music.repository import SessionRepository


@dataclass
class GetQueueQuery:
    """Query to get the queue for a guild."""

    guild_id: int


@dataclass
class QueueInfo:
    """Result containing queue information."""

    guild_id: int
    tracks: list[Track]
    current_track: Track | None
    total_duration: int | None

    @property
    def length(self) -> int:
        return len(self.tracks)

    @property
    def is_empty(self) -> bool:
        return len(self.tracks) == 0


class GetQueueHandler:
    """Handler for GetQueueQuery."""

    def __init__(self, session_repository: SessionRepository) -> None:
        self._session_repository = session_repository

    async def handle(self, query: GetQueueQuery) -> QueueInfo:
        session = await self._session_repository.get(query.guild_id)

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
