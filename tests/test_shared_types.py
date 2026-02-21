"""Unit tests for domain/shared/types.py — Pydantic Annotated type constraints."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest
from pydantic import BaseModel, ValidationError

from discord_music_player.domain.shared.types import (
    ChannelIdField,
    DiscordSnowflake,
    DurationSeconds,
    GuildIdField,
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    QueuePositionInt,
    TrackTitleStr,
    UnitInterval,
    UserIdField,
    UtcDatetimeField,
    VolumeFloat,
)


# ── Helper: build a one-field model for each type ────────────────────


def _model_for(annotation, field_name: str = "v"):
    """Dynamically create a Pydantic model with a single field of the given type."""
    return type("M", (BaseModel,), {"__annotations__": {field_name: annotation}})


# ── DiscordSnowflake ────────────────────────────────────────────────


class TestDiscordSnowflake:
    M = _model_for(DiscordSnowflake)

    def test_valid_snowflake(self):
        assert self.M(v=1).v == 1

    def test_large_valid_snowflake(self):
        assert self.M(v=2**64 - 1).v == 2**64 - 1

    def test_zero_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=0)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-1)

    def test_too_large_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=2**64)


# ── NonNegativeInt ──────────────────────────────────────────────────


class TestNonNegativeInt:
    M = _model_for(NonNegativeInt)

    def test_zero_allowed(self):
        assert self.M(v=0).v == 0

    def test_positive_allowed(self):
        assert self.M(v=42).v == 42

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-1)


# ── PositiveInt ─────────────────────────────────────────────────────


class TestPositiveInt:
    M = _model_for(PositiveInt)

    def test_one_allowed(self):
        assert self.M(v=1).v == 1

    def test_zero_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=0)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-1)


# ── NonNegativeFloat ────────────────────────────────────────────────


class TestNonNegativeFloat:
    M = _model_for(NonNegativeFloat)

    def test_zero_allowed(self):
        assert self.M(v=0.0).v == 0.0

    def test_positive_allowed(self):
        assert self.M(v=3.14).v == 3.14

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-0.01)


# ── UnitInterval ────────────────────────────────────────────────────


class TestUnitInterval:
    M = _model_for(UnitInterval)

    def test_zero_allowed(self):
        assert self.M(v=0.0).v == 0.0

    def test_one_allowed(self):
        assert self.M(v=1.0).v == 1.0

    def test_mid_allowed(self):
        assert self.M(v=0.5).v == 0.5

    def test_above_one_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=1.01)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-0.01)


# ── VolumeFloat ─────────────────────────────────────────────────────


class TestVolumeFloat:
    M = _model_for(VolumeFloat)

    def test_zero_allowed(self):
        assert self.M(v=0.0).v == 0.0

    def test_max_allowed(self):
        assert self.M(v=2.0).v == 2.0

    def test_above_max_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=2.01)

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-0.1)


# ── NonEmptyStr ─────────────────────────────────────────────────────


class TestNonEmptyStr:
    M = _model_for(NonEmptyStr)

    def test_valid_string(self):
        assert self.M(v="hello").v == "hello"

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v="")


# ── TrackTitleStr ───────────────────────────────────────────────────


class TestTrackTitleStr:
    M = _model_for(TrackTitleStr)

    def test_valid_title(self):
        assert self.M(v="My Song").v == "My Song"

    def test_empty_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v="")

    def test_max_length(self):
        title = "x" * 500
        assert self.M(v=title).v == title

    def test_over_max_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v="x" * 501)


# ── HttpUrlStr ──────────────────────────────────────────────────────


class TestHttpUrlStr:
    M = _model_for(HttpUrlStr)

    def test_https_valid(self):
        assert self.M(v="https://example.com").v == "https://example.com"

    def test_http_valid(self):
        assert self.M(v="http://example.com").v == "http://example.com"

    def test_no_scheme_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v="example.com")

    def test_ftp_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v="ftp://example.com")


# ── DurationSeconds ─────────────────────────────────────────────────


class TestDurationSeconds:
    M = _model_for(DurationSeconds)

    def test_zero_allowed(self):
        assert self.M(v=0).v == 0

    def test_max_allowed(self):
        assert self.M(v=86_400).v == 86_400

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-1)

    def test_over_max_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=86_401)


# ── QueuePositionInt ────────────────────────────────────────────────


class TestQueuePositionInt:
    M = _model_for(QueuePositionInt)

    def test_zero_allowed(self):
        assert self.M(v=0).v == 0

    def test_positive_allowed(self):
        assert self.M(v=49).v == 49

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=-1)


# ── UtcDatetimeField ───────────────────────────────────────────────


class TestUtcDatetimeField:
    M = _model_for(UtcDatetimeField)

    def test_utc_datetime_passes(self):
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        assert self.M(v=dt).v == dt

    def test_non_utc_timezone_normalised(self):
        eastern = timezone(offset=__import__("datetime").timedelta(hours=-5))
        dt = datetime(2024, 1, 1, 12, 0, tzinfo=eastern)
        result = self.M(v=dt).v
        assert result.tzinfo == UTC

    def test_naive_datetime_rejected(self):
        with pytest.raises(ValidationError):
            self.M(v=datetime(2024, 1, 1))


# ── ID field aliases ────────────────────────────────────────────────


class TestIdFieldAliases:
    """GuildIdField, UserIdField, ChannelIdField should behave as DiscordSnowflake."""

    def test_guild_id_valid(self):
        M = _model_for(GuildIdField)
        assert M(v=123456789).v == 123456789

    def test_user_id_valid(self):
        M = _model_for(UserIdField)
        assert M(v=123456789).v == 123456789

    def test_channel_id_valid(self):
        M = _model_for(ChannelIdField)
        assert M(v=123456789).v == 123456789

    def test_guild_id_zero_rejected(self):
        M = _model_for(GuildIdField)
        with pytest.raises(ValidationError):
            M(v=0)

    def test_user_id_zero_rejected(self):
        M = _model_for(UserIdField)
        with pytest.raises(ValidationError):
            M(v=0)

    def test_channel_id_zero_rejected(self):
        M = _model_for(ChannelIdField)
        with pytest.raises(ValidationError):
            M(v=0)
