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

    outcome: Literal["ok"] = "ok"
    track: Track
    position: NonNegativeInt
    queue_length: NonNegativeInt
    should_start: bool = False
    message: NonEmptyStr


class EnqueueFailure(BaseModel):
    """A rejected enqueue and the reason."""

    model_config = FrozenModelConfig

    outcome: Literal["failure"] = "failure"
    message: NonEmptyStr


EnqueueResult = Annotated[EnqueueOk | EnqueueFailure, Field(discriminator="outcome")]
"""Outcome of an enqueue: a populated ``ok`` variant or a ``failure`` with a message."""


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
