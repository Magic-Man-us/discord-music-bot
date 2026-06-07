"""DTOs for the queue application service."""

from __future__ import annotations

from pydantic import BaseModel

from ...domain.music.entities import Track
from ...domain.shared.model_config import FrozenModelConfig
from ...domain.shared.types import NonEmptyStr, NonNegativeInt


class EnqueueMeta(BaseModel):
    """Tracks the position/size context of an enqueue operation."""

    model_config = FrozenModelConfig

    track: Track
    position: NonNegativeInt
    queue_length: NonNegativeInt
    should_start: bool = False


class EnqueueResult(BaseModel):
    model_config = FrozenModelConfig

    success: bool
    meta: EnqueueMeta | None = None
    message: NonEmptyStr

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
    def failure(cls, message: NonEmptyStr) -> EnqueueResult:
        return cls(success=False, message=message)

    @classmethod
    def ok(cls, *, meta: EnqueueMeta, message: NonEmptyStr) -> EnqueueResult:
        return cls(success=True, meta=meta, message=message)


class BatchEnqueueResult(BaseModel):
    model_config = FrozenModelConfig

    enqueued: NonNegativeInt = 0
    should_start: bool = False


class QueueSnapshot(BaseModel):
    model_config = FrozenModelConfig

    current_track: Track | None
    tracks: list[Track]
    total_tracks: NonNegativeInt
    total_duration: NonNegativeInt | None
