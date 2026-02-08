"""Shared Pydantic validators for domain models.

This module provides reusable validators for common validation patterns,
particularly for Discord-specific data types like snowflake IDs.
"""

from typing import Any

from pydantic import field_validator

from discord_music_player.domain.shared.messages import ErrorMessages


def validate_discord_snowflake(value: int) -> int:
    """Validate a Discord snowflake ID.

    Discord snowflake IDs are 64-bit unsigned integers representing unique
    identifiers for users, guilds, channels, messages, etc.

    Args:
        value: The snowflake ID to validate.

    Returns:
        The validated snowflake ID.

    Raises:
        ValueError: If the snowflake ID is invalid.
    """
    if value <= 0:
        raise ValueError(ErrorMessages.INVALID_SNOWFLAKE)
    if value >= 2**64:
        raise ValueError(ErrorMessages.SNOWFLAKE_TOO_LARGE)
    return value


def validate_positive_int(value: int, field_name: str = "value") -> int:
    """Validate that an integer is positive.

    Args:
        value: The integer to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated integer.

    Raises:
        ValueError: If the integer is not positive.
    """
    if value <= 0:
        raise ValueError(ErrorMessages.FIELD_MUST_BE_POSITIVE.format(field_name=field_name))
    return value


def validate_non_empty_string(value: str, field_name: str = "value") -> str:
    """Validate that a string is not empty or whitespace-only.

    Args:
        value: The string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated string.

    Raises:
        ValueError: If the string is empty or whitespace-only.
    """
    if not value or not value.strip():
        raise ValueError(ErrorMessages.FIELD_CANNOT_BE_EMPTY.format(field_name=field_name))
    return value


class DiscordValidators:
    """Collection of Pydantic field validators for Discord-specific fields.

    This class provides reusable validator decorators that can be applied
    to Pydantic models containing Discord data types.

    Example:
        >>> from pydantic import BaseModel
        >>> class MyCommand(BaseModel):
        ...     guild_id: int
        ...     user_id: int
        ...
        ...     _validate_guild_id = DiscordValidators.snowflake("guild_id")
        ...     _validate_user_id = DiscordValidators.snowflake("user_id")
    """

    @staticmethod
    def snowflake(field_name: str) -> Any:
        """Create a field validator for a Discord snowflake ID.

        Args:
            field_name: Name of the field to validate.

        Returns:
            A Pydantic field_validator decorator configured for the field.
        """

        @field_validator(field_name)
        @classmethod
        def validator(cls, v: int) -> int:
            return validate_discord_snowflake(v)

        return validator

    @staticmethod
    def snowflakes(*field_names: str) -> Any:
        """Create a field validator for multiple Discord snowflake ID fields.

        Args:
            *field_names: Names of the fields to validate.

        Returns:
            A Pydantic field_validator decorator configured for all fields.
        """

        @field_validator(*field_names)
        @classmethod
        def validator(cls, v: int) -> int:
            return validate_discord_snowflake(v)

        return validator
