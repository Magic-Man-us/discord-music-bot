"""Shared Pydantic validators for Discord-specific data types."""

from __future__ import annotations

from typing import Any

from pydantic import field_validator

from discord_music_player.domain.shared.messages import ErrorMessages


def validate_discord_snowflake(value: int) -> int:
    """Validate a Discord snowflake ID (64-bit unsigned integer)."""
    if value <= 0:
        raise ValueError(ErrorMessages.INVALID_SNOWFLAKE)
    if value >= 2**64:
        raise ValueError(ErrorMessages.SNOWFLAKE_TOO_LARGE)
    return value


def validate_positive_int(value: int, field_name: str = "value") -> int:
    """Validate that an integer is positive."""
    if value <= 0:
        raise ValueError(ErrorMessages.FIELD_MUST_BE_POSITIVE.format(field_name=field_name))
    return value


def validate_non_empty_string(value: str, field_name: str = "value") -> str:
    """Validate that a string is not empty or whitespace-only."""
    if not value or not value.strip():
        raise ValueError(ErrorMessages.FIELD_CANNOT_BE_EMPTY.format(field_name=field_name))
    return value


class DiscordValidators:
    """Pydantic field validators for Discord snowflake IDs.

    Example:
        >>> class MyCommand(BaseModel):
        ...     guild_id: int
        ...     _validate_guild_id = DiscordValidators.snowflake("guild_id")
    """

    @staticmethod
    def snowflake(field_name: str) -> Any:
        """Create a snowflake validator for a single field."""

        @field_validator(field_name)
        @classmethod
        def validator(cls, v: int) -> int:
            return validate_discord_snowflake(v)

        return validator

    @staticmethod
    def snowflakes(*field_names: str) -> Any:
        """Create a snowflake validator for multiple fields."""

        @field_validator(*field_names)
        @classmethod
        def validator(cls, v: int) -> int:
            return validate_discord_snowflake(v)

        return validator
