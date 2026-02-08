"""
Validators Tests for Coverage

Tests for shared validators and Discord-specific validation logic.
"""

import pytest
from pydantic import BaseModel

from discord_music_player.domain.shared.validators import (
    DiscordValidators,
    validate_discord_snowflake,
    validate_non_empty_string,
    validate_positive_int,
)


class TestValidateDiscordSnowflake:
    """Tests for Discord snowflake ID validation."""

    def test_valid_snowflake(self):
        """Should accept valid snowflake IDs."""
        result = validate_discord_snowflake(123456789012345678)
        assert result == 123456789012345678

    def test_rejects_zero(self):
        """Should reject zero."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_discord_snowflake(0)

    def test_rejects_negative(self):
        """Should reject negative IDs."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_discord_snowflake(-1)

    def test_rejects_too_large(self):
        """Should reject IDs >= 2^64."""
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_discord_snowflake(2**64)


class TestValidatePositiveInt:
    """Tests for positive integer validation."""

    def test_valid_positive_int(self):
        """Should accept positive integers."""
        result = validate_positive_int(42)
        assert result == 42

    def test_rejects_zero(self):
        """Should reject zero."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_positive_int(0)

    def test_rejects_negative(self):
        """Should reject negative integers."""
        with pytest.raises(ValueError, match="must be positive"):
            validate_positive_int(-1)

    def test_custom_field_name(self):
        """Should use custom field name in error message."""
        with pytest.raises(ValueError, match="count"):
            validate_positive_int(0, field_name="count")


class TestValidateNonEmptyString:
    """Tests for non-empty string validation."""

    def test_valid_string(self):
        """Should accept non-empty strings."""
        result = validate_non_empty_string("hello")
        assert result == "hello"

    def test_rejects_empty_string(self):
        """Should reject empty strings."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_non_empty_string("")

    def test_rejects_whitespace_only(self):
        """Should reject whitespace-only strings."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_non_empty_string("   ")

    def test_accepts_string_with_whitespace(self):
        """Should accept strings with leading/trailing whitespace."""
        result = validate_non_empty_string("  hello  ")
        assert result == "  hello  "

    def test_custom_field_name(self):
        """Should use custom field name in error message."""
        with pytest.raises(ValueError, match="title"):
            validate_non_empty_string("", field_name="title")


class TestDiscordValidators:
    """Tests for DiscordValidators class."""

    def test_snowflake_single_field(self):
        """Should create validator for single snowflake field."""

        class TestModel(BaseModel):
            guild_id: int

            _validate_guild_id = DiscordValidators.snowflake("guild_id")

        # Valid
        model = TestModel(guild_id=123456789)
        assert model.guild_id == 123456789

        # Invalid
        with pytest.raises(ValueError):
            TestModel(guild_id=0)

    def test_snowflakes_multiple_fields(self):
        """Should create validator for multiple snowflake fields."""

        class TestModel(BaseModel):
            guild_id: int
            user_id: int
            channel_id: int

            _validate_ids = DiscordValidators.snowflakes("guild_id", "user_id", "channel_id")

        # Valid
        model = TestModel(guild_id=111, user_id=222, channel_id=333)
        assert model.guild_id == 111
        assert model.user_id == 222
        assert model.channel_id == 333

        # Invalid guild_id
        with pytest.raises(ValueError):
            TestModel(guild_id=0, user_id=222, channel_id=333)

        # Invalid user_id
        with pytest.raises(ValueError):
            TestModel(guild_id=111, user_id=-1, channel_id=333)
