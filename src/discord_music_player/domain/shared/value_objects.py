"""Strongly-typed identifiers used across all bounded contexts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.shared.messages import ErrorMessages
from discord_music_player.domain.shared.types import DiscordSnowflake


class GuildId(BaseModel):
    """Strongly-typed Discord guild (server) identifier."""

    model_config = ConfigDict(frozen=True)

    value: DiscordSnowflake

    def __init__(self, value: int | None = None, /, **kwargs: object) -> None:
        if value is not None and "value" not in kwargs:
            kwargs["value"] = value
        super().__init__(**kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GuildId):
            return self.value == other.value
        return NotImplemented


class UserId(BaseModel):
    """Strongly-typed Discord user identifier."""

    model_config = ConfigDict(frozen=True)

    value: DiscordSnowflake

    def __init__(self, value: int | None = None, /, **kwargs: object) -> None:
        if value is not None and "value" not in kwargs:
            kwargs["value"] = value
        super().__init__(**kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UserId):
            return self.value == other.value
        return NotImplemented


class ChannelId(BaseModel):
    """Strongly-typed Discord channel identifier."""

    model_config = ConfigDict(frozen=True)

    value: DiscordSnowflake

    def __init__(self, value: int | None = None, /, **kwargs: object) -> None:
        if value is not None and "value" not in kwargs:
            kwargs["value"] = value
        super().__init__(**kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ChannelId):
            return self.value == other.value
        return NotImplemented
