"""Strongly-typed identifiers used across all bounded contexts.

Uses a generic ``ValueWrapper`` base to eliminate boilerplate for
single-field frozen value objects that need positional construction,
hashing, and equality.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.shared.types import DiscordSnowflake

T = TypeVar("T")


class ValueWrapper(BaseModel, Generic[T]):
    """Generic base for single-field frozen value objects.

    Provides positional construction (``GuildId(123)``), hashing, equality,
    and str/int conversions.  Subclass and override ``value`` type as needed.
    """

    model_config = ConfigDict(frozen=True)

    value: T  # type: ignore[misc]

    def __init__(self, value: T | None = None, /, **kwargs: object) -> None:
        if value is not None and "value" not in kwargs:
            kwargs["value"] = value
        super().__init__(**kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return int(self.value)  # type: ignore[arg-type]

    def __hash__(self) -> int:
        return hash(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, type(self)):
            return self.value == other.value
        return NotImplemented


class GuildId(ValueWrapper[DiscordSnowflake]):
    """Strongly-typed Discord guild (server) identifier."""


class UserId(ValueWrapper[DiscordSnowflake]):
    """Strongly-typed Discord user identifier."""


class ChannelId(ValueWrapper[DiscordSnowflake]):
    """Strongly-typed Discord channel identifier."""
