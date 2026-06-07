"""DTOs for the queue application service."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ...domain.music.entities import Track
from ...domain.shared.model_config import FrozenModelConfig
from ...domain.shared.types import NonEmptyStr, NonNegativeInt


class EnqueueOk(BaseModel):
    """A successful enqueue: the queued track and its position context."""

    model_config = FrozenModelConfig

    success: Literal[True] = True
    track: Track
    position: NonNegativeInt
    queue_length: NonNegativeInt
    should_start: bool = False
    message: NonEmptyStr


class EnqueueFailure(BaseModel):
    """A rejected enqueue and the reason."""

    model_config = FrozenModelConfig

    success: Literal[False] = False
    message: NonEmptyStr


EnqueueResult = Annotated[EnqueueOk | EnqueueFailure, Field(discriminator="success")]
"""Outcome of an enqueue, discriminated on ``success``: a populated ``ok`` or a ``failure``."""


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
