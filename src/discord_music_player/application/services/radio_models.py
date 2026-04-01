"""DTOs for the radio application service."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...domain.music.entities import Track
from ...domain.recommendations.entities import Recommendation
from ...domain.shared.types import DiscordSnowflake, NonEmptyStr, NonNegativeInt, TrackTitleStr


class RadioState(BaseModel):
    """Mutable per-guild state for an active radio session.

    Holds the unresolved recommendation pool so tracks can be resolved
    on-demand as the queue is consumed, without extra AI calls.
    """

    model_config = ConfigDict()

    enabled: bool = False
    seed_track_title: TrackTitleStr | None = None
    tracks_consumed: NonNegativeInt = 0
    pool: list[Recommendation] = Field(default_factory=list)
    user_id: DiscordSnowflake | None = None
    user_name: NonEmptyStr | None = None
    channel_id: DiscordSnowflake | None = None

    @property
    def effective_user_id(self) -> DiscordSnowflake:
        return self.user_id or 0

    @property
    def effective_user_name(self) -> str:
        return self.user_name or "Radio"


class RadioToggleResult(BaseModel):
    model_config = ConfigDict()

    enabled: bool
    tracks_added: NonNegativeInt = 0
    generated_tracks: list[Track] = []
    seed_title: TrackTitleStr | None = None
    message: NonEmptyStr = "Radio toggled."
