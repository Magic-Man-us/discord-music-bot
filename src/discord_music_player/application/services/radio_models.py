"""DTOs for the radio application service."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ...domain.music.entities import Track
from ...domain.recommendations.entities import Recommendation
from ...domain.shared.model_config import FrozenModelConfig, MutableModelConfig
from ...domain.shared.types import DiscordSnowflake, NonEmptyStr, NonNegativeInt, TrackTitleStr


class RadioState(BaseModel):
    """Mutable per-guild state for an active radio session.

    Holds the unresolved recommendation pool so tracks can be resolved
    on-demand as the queue is consumed, without extra AI calls.
    """

    model_config = MutableModelConfig

    enabled: bool = False
    seed_track_title: TrackTitleStr | None = None
    tracks_consumed: NonNegativeInt = 0
    pool: list[Recommendation] = Field(default_factory=list)
    user_id: DiscordSnowflake | None = None
    user_name: NonEmptyStr | None = None
    channel_id: DiscordSnowflake | None = None

    @property
    def effective_user_id(self) -> DiscordSnowflake | None:
        return self.user_id

    @property
    def effective_user_name(self) -> str:
        return self.user_name or "Radio"


class RadioEnabled(BaseModel):
    """Radio is on: the freshly queued tracks and the seed."""

    model_config = FrozenModelConfig

    enabled: Literal[True] = True
    tracks_added: NonNegativeInt = 0
    generated_tracks: list[Track] = Field(default_factory=list)
    seed_title: TrackTitleStr | None = None
    message: NonEmptyStr = "Radio enabled."


class RadioDisabled(BaseModel):
    """Radio is off, or could not be enabled, with the reason."""

    model_config = FrozenModelConfig

    enabled: Literal[False] = False
    message: NonEmptyStr


RadioToggleResult = Annotated[RadioEnabled | RadioDisabled, Field(discriminator="enabled")]
"""Outcome of a radio toggle/continue, discriminated on ``enabled`` (mirrors RadioState.enabled)."""
