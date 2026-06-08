"""Typed, tagged models for Discord presence activities.

discord.py owns the activity classes (Spotify, Activity, ...); ``from_activity``
narrows each into a ``kind``-tagged variant at the boundary so the rest of the
code dispatches on this discriminated union instead of re-checking foreign types.
"""

from __future__ import annotations

from typing import Annotated, Literal

import discord
from pydantic import BaseModel, Field

from ....domain.shared.model_config import FrozenModelConfig
from ....domain.shared.types import DiscordSnowflake, NonEmptyStr, OptionalNonEmptyStr


class SpotifyDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["spotify"] = "spotify"
    title: OptionalNonEmptyStr = None
    artist: OptionalNonEmptyStr = None
    album: OptionalNonEmptyStr = None
    track_id: OptionalNonEmptyStr = None


class CustomDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["custom"] = "custom"
    name: OptionalNonEmptyStr = None
    emoji: OptionalNonEmptyStr = None


class StreamingDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["streaming"] = "streaming"
    name: OptionalNonEmptyStr = None
    url: OptionalNonEmptyStr = None
    platform: OptionalNonEmptyStr = None


class GenericDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["generic"] = "generic"
    name: OptionalNonEmptyStr = None
    details: OptionalNonEmptyStr = None
    state: OptionalNonEmptyStr = None
    app_id: DiscordSnowflake | None = None


class UnknownDetail(BaseModel):
    model_config = FrozenModelConfig

    kind: Literal["unknown"] = "unknown"
    repr: NonEmptyStr


ActivityDetail = Annotated[
    SpotifyDetail | CustomDetail | StreamingDetail | GenericDetail | UnknownDetail,
    Field(discriminator="kind"),
]


class ActivityInfo(BaseModel):
    model_config = FrozenModelConfig

    class_name: NonEmptyStr
    type_name: NonEmptyStr
    detail: ActivityDetail

    @classmethod
    def from_activity(
        cls,
        act: discord.Activity
        | discord.Game
        | discord.Streaming
        | discord.CustomActivity
        | discord.Spotify,
    ) -> ActivityInfo:
        # discord.py owns these classes; this boundary match is the only place we
        # dispatch on them — past here every activity is a tagged ActivityDetail.
        detail: ActivityDetail
        match act:
            case discord.Spotify():
                detail = SpotifyDetail(
                    title=act.title, artist=act.artist, album=act.album, track_id=act.track_id
                )
            case discord.CustomActivity():
                detail = CustomDetail(name=act.name, emoji=str(act.emoji) if act.emoji else None)
            case discord.Streaming():
                detail = StreamingDetail(name=act.name, url=act.url, platform=act.platform)
            case discord.Activity():
                detail = GenericDetail(
                    name=act.name,
                    details=act.details,
                    state=act.state,
                    app_id=act.application_id,
                )
            case _:
                detail = UnknownDetail(repr=repr(act))
        return cls(class_name=type(act).__name__, type_name=act.type.name, detail=detail)
