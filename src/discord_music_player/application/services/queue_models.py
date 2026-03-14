"""DTOs for the queue application service."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...domain.music.entities import Track
from ...domain.shared.types import NonNegativeInt


class EnqueueMeta(BaseModel):
    """Tracks the position/size context of an enqueue operation."""

    model_config = ConfigDict(frozen=True)

    track: Track
    position: NonNegativeInt
    queue_length: NonNegativeInt
    should_start: bool = False


class EnqueueResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    meta: EnqueueMeta | None = None
    message: str = ""

    @property
    def track(self) -> Track | None:
        return self.meta.track if self.meta else None

    @property
    def position(self) -> int:
        return self.meta.position if self.meta else 0

    @property
    def queue_length(self) -> int:
        return self.meta.queue_length if self.meta else 0

    @property
    def should_start(self) -> bool:
        return self.meta.should_start if self.meta else False

    @classmethod
    def failure(cls, message: str) -> EnqueueResult:
        return cls(success=False, message=message)

    @classmethod
    def ok(cls, *, meta: EnqueueMeta, message: str) -> EnqueueResult:
        return cls(success=True, meta=meta, message=message)


class BatchEnqueueResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    enqueued: NonNegativeInt = 0
    should_start: bool = False


class QueueSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    current_track: Track | None
    tracks: list[Track]
    total_tracks: NonNegativeInt
    total_duration: NonNegativeInt | None
