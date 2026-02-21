"""DTOs for the radio application service."""

from __future__ import annotations

from pydantic import BaseModel

from ...domain.music.entities import Track
from ...domain.shared.types import NonEmptyStr, NonNegativeInt, TrackTitleStr


class RadioState(BaseModel):

    enabled: bool = False
    seed_track_title: TrackTitleStr | None = None
    tracks_generated: NonNegativeInt = 0


class RadioToggleResult(BaseModel):
    model_config = {"arbitrary_types_allowed": True}

    enabled: bool
    tracks_added: NonNegativeInt = 0
    generated_tracks: list[Track] = []
    seed_title: TrackTitleStr | None = None
    message: NonEmptyStr = "Radio toggled."
