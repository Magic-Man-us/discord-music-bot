"""DTOs for the radio application service."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...domain.music.entities import Track
from ...domain.shared.types import NonEmptyStr, NonNegativeInt, TrackTitleStr


class RadioState(BaseModel):
    """Mutable state tracker for a guild's radio session — mutated in-place by RadioService."""

    model_config = ConfigDict()

    enabled: bool = False
    seed_track_title: TrackTitleStr | None = None
    tracks_generated: NonNegativeInt = 0


class RadioToggleResult(BaseModel):
    model_config = ConfigDict()

    enabled: bool
    tracks_added: NonNegativeInt = 0
    generated_tracks: list[Track] = []
    seed_title: TrackTitleStr | None = None
    message: NonEmptyStr = "Radio toggled."
