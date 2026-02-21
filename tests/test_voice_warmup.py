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

    def test_negative_warmup_seconds_raises(self) -> None:
        with pytest.raises(ValueError):
            VoiceWarmupTracker(warmup_seconds=-1)

    def test_remaining_seconds_naive_now_raises(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        tracker.mark_joined(guild_id=1, user_id=2)
        naive_now = datetime.now()
        with pytest.raises(ValueError, match="timezone-aware"):
            tracker.remaining_seconds(guild_id=1, user_id=2, now=naive_now)

    def test_is_blocked_true_during_warmup(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        joined_at = datetime.now(UTC)
        tracker.mark_joined(guild_id=1, user_id=2, joined_at=joined_at)

        now = joined_at + timedelta(seconds=10)
        assert tracker.is_blocked(guild_id=1, user_id=2, now=now) is True

    def test_is_blocked_false_after_warmup(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        joined_at = datetime.now(UTC)
        tracker.mark_joined(guild_id=1, user_id=2, joined_at=joined_at)

        now = joined_at + timedelta(seconds=61)
        assert tracker.is_blocked(guild_id=1, user_id=2, now=now) is False

    def test_is_blocked_false_no_record(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        assert tracker.is_blocked(guild_id=1, user_id=2) is False

    def test_clear_removes_warmup_state(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        tracker.mark_joined(guild_id=1, user_id=2)
        assert tracker.is_blocked(guild_id=1, user_id=2) is True

        tracker.clear(guild_id=1, user_id=2)
        assert tracker.is_blocked(guild_id=1, user_id=2) is False
        assert tracker.remaining_seconds(guild_id=1, user_id=2) == 0

    def test_clear_nonexistent_user_is_noop(self) -> None:
        tracker = VoiceWarmupTracker(warmup_seconds=60)
        tracker.clear(guild_id=1, user_id=999)  # should not raise
