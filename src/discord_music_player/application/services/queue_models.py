"""DTOs for the queue application service."""

from __future__ import annotations

from pydantic import BaseModel

from ...domain.music.entities import Track
from ...domain.shared.types import NonNegativeInt


class EnqueueResult(BaseModel):
    success: bool
    track: Track | None = None
    position: NonNegativeInt = 0
    queue_length: NonNegativeInt = 0
    message: str = ""
    should_start: bool = False


class QueueInfo(BaseModel):

    current_track: Track | None
    upcoming_tracks: list[Track]
    total_length: NonNegativeInt
    total_duration_seconds: NonNegativeInt | None

    @property
    def tracks(self) -> list[Track]:
        return self.upcoming_tracks

    @property
    def total_tracks(self) -> int:
        return self.total_length

    @property
    def total_duration(self) -> int | None:
        return self.total_duration_seconds
