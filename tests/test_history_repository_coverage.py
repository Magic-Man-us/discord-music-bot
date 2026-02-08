"""
Additional History Repository Tests for Coverage

Tests edge cases and uncovered code paths in TrackHistoryRepository.
"""

from datetime import UTC, datetime, timedelta

import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId


class TestHistoryRepositoryEdgeCases:
    """Tests for history repository edge cases and uncovered paths."""

    @pytest.fixture
    def sample_track(self):
        """Create a sample track."""
        return Track(
            id=TrackId("test123"),
            title="Test Song",
            webpage_url="https://youtube.com/watch?v=test",
            stream_url="https://stream.example.com/audio",
            duration_seconds=180,
            artist="Test Artist",
            requested_by_id=12345,
            requested_by_name="TestUser",
        )

    async def test_record_play_with_custom_timestamp(self, history_repository, sample_track):
        """Should record play with custom timestamp."""
        guild_id = 123
        custom_time = datetime.now(UTC) - timedelta(hours=1)

        await history_repository.record_play(guild_id, sample_track, played_at=custom_time)

        # Get recent and verify timestamp
        recent = await history_repository.get_recent(guild_id, limit=1)
        assert len(recent) == 1

    async def test_get_recent_returns_empty_for_no_history(self, history_repository):
        """Should return empty list when no history exists."""
        result = await history_repository.get_recent(guild_id=999, limit=10)

        assert result == []

    async def test_get_recent_respects_limit(self, history_repository, sample_track):
        """Should respect the limit parameter."""
        guild_id = 123

        # Record 10 plays
        for i in range(10):
            track = sample_track.model_copy(
                update={"id": TrackId(f"track{i}"), "title": f"Song {i}"}
            )
            await history_repository.record_play(guild_id, track)

        # Request only 5
        recent = await history_repository.get_recent(guild_id, limit=5)

        assert len(recent) == 5

    async def test_get_play_count_returns_zero_for_new_track(self, history_repository):
        """Should return 0 for tracks that haven't been played."""
        count = await history_repository.get_play_count(guild_id=123, track_id=TrackId("never_played"))

        assert count == 0

    async def test_get_play_count_counts_multiple_plays(self, history_repository, sample_track):
        """Should count multiple plays of the same track."""
        guild_id = 123
        track_id = sample_track.id

        # Play the same track 5 times
        for _ in range(5):
            await history_repository.record_play(guild_id, sample_track)

        count = await history_repository.get_play_count(guild_id, track_id)

        assert count == 5

    async def test_get_most_played_returns_empty_for_no_history(self, history_repository):
        """Should return empty list when no history exists."""
        result = await history_repository.get_most_played(guild_id=999, limit=10)

        assert result == []

    async def test_get_most_played_sorts_by_play_count(self, history_repository):
        """Should return tracks sorted by play count."""
        guild_id = 123

        # Create tracks with different play counts
        track1 = Track(
            id=TrackId("track1"),
            title="Popular Song",
            webpage_url="https://youtube.com/1",
        )
        track2 = Track(
            id=TrackId("track2"),
            title="Less Popular Song",
            webpage_url="https://youtube.com/2",
        )
        track3 = Track(
            id=TrackId("track3"),
            title="Least Popular Song",
            webpage_url="https://youtube.com/3",
        )

        # Play them different amounts
        for _ in range(5):
            await history_repository.record_play(guild_id, track1)  # 5 plays
        for _ in range(3):
            await history_repository.record_play(guild_id, track2)  # 3 plays
        await history_repository.record_play(guild_id, track3)  # 1 play

        # Get most played
        most_played = await history_repository.get_most_played(guild_id, limit=10)

        assert len(most_played) == 3
        assert most_played[0][1] == 5  # First has 5 plays
        assert most_played[1][1] == 3  # Second has 3 plays
        assert most_played[2][1] == 1  # Third has 1 play

    async def test_clear_history_removes_all_guild_entries(self, history_repository, sample_track):
        """Should remove all history for a specific guild."""
        guild1 = 123
        guild2 = 456

        # Add history to both guilds
        await history_repository.record_play(guild1, sample_track)
        await history_repository.record_play(guild2, sample_track)

        # Clear guild1
        count = await history_repository.clear_history(guild1)

        assert count == 1

        # Guild1 should have no history
        guild1_history = await history_repository.get_recent(guild1)
        assert len(guild1_history) == 0

        # Guild2 should still have history
        guild2_history = await history_repository.get_recent(guild2)
        assert len(guild2_history) == 1

    async def test_mark_finished_updates_most_recent_play(self, history_repository, sample_track):
        """Should mark the most recent play as finished."""
        guild_id = 123
        track_id = sample_track.id

        # Record a play
        await history_repository.record_play(guild_id, sample_track)

        # Mark it as finished
        await history_repository.mark_finished(guild_id, track_id, skipped=False)

        # This is mostly for code coverage - actual verification would require
        # checking the database directly since we don't expose finished_at

    async def test_mark_finished_with_skip_flag(self, history_repository, sample_track):
        """Should mark play as skipped."""
        guild_id = 123
        track_id = sample_track.id

        # Record a play
        await history_repository.record_play(guild_id, sample_track)

        # Mark it as skipped
        await history_repository.mark_finished(guild_id, track_id, skipped=True)

    async def test_cleanup_old_removes_old_entries(self, history_repository, sample_track):
        """Should remove history entries older than cutoff."""
        guild_id = 123

        # Record old play
        old_time = datetime.now(UTC) - timedelta(days=60)
        await history_repository.record_play(guild_id, sample_track, played_at=old_time)

        # Record recent play
        recent_track = sample_track.model_copy(
            update={"id": TrackId("recent"), "title": "Recent Song"}
        )
        await history_repository.record_play(guild_id, recent_track)

        # Cleanup entries older than 30 days
        cutoff = datetime.now(UTC) - timedelta(days=30)
        count = await history_repository.cleanup_old(cutoff)

        assert count == 1

        # Should only have the recent track
        history = await history_repository.get_recent(guild_id)
        assert len(history) == 1
        assert history[0].title == "Recent Song"

    async def test_cleanup_old_with_no_old_entries(self, history_repository, sample_track):
        """Should return 0 when no old entries exist."""
        guild_id = 123

        # Record recent play
        await history_repository.record_play(guild_id, sample_track)

        # Try to cleanup entries older than 30 days
        cutoff = datetime.now(UTC) - timedelta(days=30)
        count = await history_repository.cleanup_old(cutoff)

        assert count == 0

    async def test_get_most_played_respects_limit(self, history_repository):
        """Should respect limit parameter in get_most_played."""
        guild_id = 123

        # Create 10 different tracks
        for i in range(10):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Song {i}",
                webpage_url=f"https://youtube.com/{i}",
            )
            # Each track played (10-i) times to have descending play counts
            for _ in range(10 - i):
                await history_repository.record_play(guild_id, track)

        # Request only top 3
        most_played = await history_repository.get_most_played(guild_id, limit=3)

        assert len(most_played) == 3
        # Should have highest play counts
        assert most_played[0][1] == 10
        assert most_played[1][1] == 9
        assert most_played[2][1] == 8
