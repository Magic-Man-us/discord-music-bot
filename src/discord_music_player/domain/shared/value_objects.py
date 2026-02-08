"""Strongly-typed identifiers used across all bounded contexts."""

from __future__ import annotations

from dataclasses import dataclass

from discord_music_player.domain.shared.messages import ErrorMessages


@dataclass(frozen=True)
class GuildId:
    """Strongly-typed Discord guild (server) identifier."""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(ErrorMessages.INVALID_GUILD_ID)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class UserId:
    """Strongly-typed Discord user identifier."""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(ErrorMessages.INVALID_USER_ID)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class ChannelId:
    """Strongly-typed Discord channel identifier."""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(ErrorMessages.INVALID_CHANNEL_ID)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
