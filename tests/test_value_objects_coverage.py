"""
Value Objects Tests for Coverage

Tests for shared value objects (GuildId, UserId, ChannelId).
"""

import pytest

from discord_music_player.domain.shared.value_objects import ChannelId, GuildId, UserId


class TestGuildId:
    """Tests for GuildId value object."""

    def test_create_valid_guild_id(self):
        """Should create GuildId with valid value."""
        guild_id = GuildId(123456789)
        assert guild_id.value == 123456789

    def test_rejects_zero(self):
        """Should reject zero."""
        with pytest.raises(ValueError):
            GuildId(0)

    def test_rejects_negative(self):
        """Should reject negative values."""
        with pytest.raises(ValueError):
            GuildId(-1)

    def test_str_conversion(self):
        """Should convert to string."""
        guild_id = GuildId(123456789)
        assert str(guild_id) == "123456789"

    def test_int_conversion(self):
        """Should convert to int."""
        guild_id = GuildId(123456789)
        assert int(guild_id) == 123456789

    def test_immutable(self):
        """Should be immutable (frozen)."""
        guild_id = GuildId(123456789)
        with pytest.raises(Exception):  # FrozenInstanceError
            guild_id.value = 999

    def test_equality(self):
        """Should compare by value."""
        guild_id1 = GuildId(123)
        guild_id2 = GuildId(123)
        guild_id3 = GuildId(456)

        assert guild_id1 == guild_id2
        assert guild_id1 != guild_id3


class TestUserId:
    """Tests for UserId value object."""

    def test_create_valid_user_id(self):
        """Should create UserId with valid value."""
        user_id = UserId(987654321)
        assert user_id.value == 987654321

    def test_rejects_zero(self):
        """Should reject zero."""
        with pytest.raises(ValueError):
            UserId(0)

    def test_rejects_negative(self):
        """Should reject negative values."""
        with pytest.raises(ValueError):
            UserId(-1)

    def test_str_conversion(self):
        """Should convert to string."""
        user_id = UserId(987654321)
        assert str(user_id) == "987654321"

    def test_int_conversion(self):
        """Should convert to int."""
        user_id = UserId(987654321)
        assert int(user_id) == 987654321

    def test_immutable(self):
        """Should be immutable (frozen)."""
        user_id = UserId(987654321)
        with pytest.raises(Exception):  # FrozenInstanceError
            user_id.value = 999

    def test_equality(self):
        """Should compare by value."""
        user_id1 = UserId(123)
        user_id2 = UserId(123)
        user_id3 = UserId(456)

        assert user_id1 == user_id2
        assert user_id1 != user_id3


class TestChannelId:
    """Tests for ChannelId value object."""

    def test_create_valid_channel_id(self):
        """Should create ChannelId with valid value."""
        channel_id = ChannelId(555666777)
        assert channel_id.value == 555666777

    def test_rejects_zero(self):
        """Should reject zero."""
        with pytest.raises(ValueError):
            ChannelId(0)

    def test_rejects_negative(self):
        """Should reject negative values."""
        with pytest.raises(ValueError):
            ChannelId(-1)

    def test_str_conversion(self):
        """Should convert to string."""
        channel_id = ChannelId(555666777)
        assert str(channel_id) == "555666777"

    def test_int_conversion(self):
        """Should convert to int."""
        channel_id = ChannelId(555666777)
        assert int(channel_id) == 555666777

    def test_immutable(self):
        """Should be immutable (frozen)."""
        channel_id = ChannelId(555666777)
        with pytest.raises(Exception):  # FrozenInstanceError
            channel_id.value = 999

    def test_equality(self):
        """Should compare by value."""
        channel_id1 = ChannelId(123)
        channel_id2 = ChannelId(123)
        channel_id3 = ChannelId(456)

        assert channel_id1 == channel_id2
        assert channel_id1 != channel_id3
