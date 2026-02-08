"""Unit tests for voice warmup gating."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from discord_music_player.infrastructure.discord.services.voice_warmup import VoiceWarmupTracker


class TestVoiceWarmupTracker:
    def test_remaining_seconds_no_record(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        assert tracker.remaining_seconds(guild_id=1, user_id=2) == 0

    def test_remaining_seconds_zero_warmup(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=0)
        tracker.mark_joined(guild_id=1, user_id=2)
        assert tracker.remaining_seconds(guild_id=1, user_id=2) == 0

    def test_remaining_seconds_counts_down(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        joined_at = datetime.now(UTC)
        tracker.mark_joined(guild_id=1, user_id=2, joined_at=joined_at)

        now = joined_at + timedelta(seconds=10)
        assert tracker.remaining_seconds(guild_id=1, user_id=2, now=now) == 50

    def test_remaining_seconds_ceil_behavior(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        joined_at = datetime.now(UTC)
        tracker.mark_joined(guild_id=1, user_id=2, joined_at=joined_at)

        now = joined_at + timedelta(seconds=10, milliseconds=1)
        assert tracker.remaining_seconds(guild_id=1, user_id=2, now=now) == 50

    def test_invalid_naive_datetime_raises(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        naive = datetime.now()
        with pytest.raises(ValueError, match="timezone-aware"):
            tracker.mark_joined(guild_id=1, user_id=2, joined_at=naive)
