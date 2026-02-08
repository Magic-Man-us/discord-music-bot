"""
Additional Vote Repository Tests for Coverage

Tests edge cases and uncovered code paths in VoteSessionRepository.
"""

from datetime import UTC, datetime, timedelta

import pytest

from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.value_objects import VoteType


class TestVoteRepositoryEdgeCases:
    """Tests for vote repository edge cases and uncovered paths."""

    @pytest.fixture
    def sample_vote_session(self):
        """Create a sample vote session."""
        return VoteSession(
            guild_id=123,
            track_id="test_track_123",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC),
        )

    async def test_delete_by_track_returns_false_when_no_session(self, vote_repository):
        """Should return False when no session exists for the track."""
        result = await vote_repository.delete_by_track(guild_id=999, track_id="nonexistent")

        assert result is False

    async def test_delete_by_track_deletes_existing_session(
        self, vote_repository, sample_vote_session
    ):
        """Should delete session for the given track."""
        # Save a session
        await vote_repository.save(sample_vote_session)

        # Delete by track
        result = await vote_repository.delete_by_track(guild_id=123, track_id="test_track_123")

        assert result is True

        # Verify it's gone
        session = await vote_repository.get_active(123, "test_track_123")
        assert session is None

    async def test_get_returns_none_for_expired_session(self, vote_repository):
        """Should delete and return None for expired sessions."""
        # Create an expired session (started 10 minutes ago with 5 min expiry)
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        expired_session = VoteSession(
            guild_id=123,
            track_id="test_track",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=old_time,
        )

        await vote_repository.save(expired_session)

        # Get should delete it and return None
        result = await vote_repository.get(123, VoteType.SKIP)

        assert result is None

    async def test_get_or_create_with_different_track_replaces_session(self, vote_repository):
        """Should replace session when track_id changes."""
        # Create session for track A
        session_a = VoteSession(
            guild_id=123,
            track_id="track_a",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC),
        )
        await vote_repository.save(session_a)

        # Get or create for track B (different track)
        session_b = await vote_repository.get_or_create(
            guild_id=123, track_id="track_b", vote_type=VoteType.SKIP, threshold=3
        )

        assert session_b.track_id == "track_b"

        # Verify the session now has the new track
        retrieved = await vote_repository.get(123, VoteType.SKIP)
        assert retrieved is not None
        assert retrieved.track_id == "track_b"

    async def test_get_or_create_updates_threshold_for_existing(
        self, vote_repository, sample_vote_session
    ):
        """Should update threshold if it changes for existing session."""
        # Save session with threshold=3
        await vote_repository.save(sample_vote_session)

        # Get or create with new threshold=5
        updated_session = await vote_repository.get_or_create(
            guild_id=123,
            track_id="test_track_123",
            vote_type=VoteType.SKIP,
            threshold=5,
        )

        assert updated_session.threshold == 5

        # Verify in database
        retrieved = await vote_repository.get(123, VoteType.SKIP)
        assert retrieved is not None
        assert retrieved.threshold == 5

    async def test_get_or_create_returns_existing_with_same_params(
        self, vote_repository, sample_vote_session
    ):
        """Should return existing session when params match."""
        # Save session
        await vote_repository.save(sample_vote_session)

        # Get or create with same params
        existing = await vote_repository.get_or_create(
            guild_id=123,
            track_id="test_track_123",
            vote_type=VoteType.SKIP,
            threshold=3,
        )

        assert existing.track_id == sample_vote_session.track_id
        assert existing.threshold == sample_vote_session.threshold

    async def test_get_or_create_creates_new_when_none_exists(self, vote_repository):
        """Should create new session when none exists."""
        session = await vote_repository.get_or_create(
            guild_id=456, track_id="new_track", vote_type=VoteType.SKIP, threshold=4
        )

        assert session.guild_id == 456
        assert session.track_id == "new_track"
        assert session.threshold == 4

        # Verify it's saved
        retrieved = await vote_repository.get(456, VoteType.SKIP)
        assert retrieved is not None

    async def test_save_updates_existing_session(self, vote_repository):
        """Should update existing session instead of creating duplicate."""
        # Create initial session
        session = VoteSession(
            guild_id=123,
            track_id="track_1",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC),
        )
        await vote_repository.save(session)

        # Modify and save again
        session.track_id = "track_2"
        session.threshold = 5
        await vote_repository.save(session)

        # Verify the session was updated
        retrieved = await vote_repository.get(123, VoteType.SKIP)
        assert retrieved is not None
        assert retrieved.track_id == "track_2"
        assert retrieved.threshold == 5

    async def test_delete_returns_true_when_session_deleted(
        self, vote_repository, sample_vote_session
    ):
        """Should return True when session is successfully deleted."""
        await vote_repository.save(sample_vote_session)

        result = await vote_repository.delete(123, VoteType.SKIP)

        assert result is True

    async def test_delete_returns_false_when_no_session(self, vote_repository):
        """Should return False when no session exists to delete."""
        result = await vote_repository.delete(999, VoteType.SKIP)

        assert result is False

    async def test_save_sessions_for_different_guilds(self, vote_repository):
        """Should store sessions independently for different guilds."""
        # Create sessions for different guilds
        session1 = VoteSession(
            guild_id=123,
            track_id="track_1",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC),
        )
        session2 = VoteSession(
            guild_id=456,
            track_id="track_2",
            vote_type=VoteType.STOP,
            threshold=2,
            started_at=datetime.now(UTC),
        )

        await vote_repository.save(session1)
        await vote_repository.save(session2)

        # Verify both sessions exist independently
        retrieved1 = await vote_repository.get(123, VoteType.SKIP)
        retrieved2 = await vote_repository.get(456, VoteType.STOP)

        assert retrieved1 is not None
        assert retrieved1.track_id == "track_1"
        assert retrieved2 is not None
        assert retrieved2.track_id == "track_2"

    async def test_cleanup_expired_removes_old_sessions(self, vote_repository):
        """Should remove expired vote sessions."""
        # Create an expired session (started long ago)
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        old_session = VoteSession(
            guild_id=123,
            track_id="old_track",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=old_time,
        )
        await vote_repository.save(old_session)

        # Cleanup expired sessions (default expiration is 5 minutes)
        count = await vote_repository.cleanup_expired()

        assert count >= 1

    async def test_complete_session_marks_as_completed(self, vote_repository, sample_vote_session):
        """Should mark session as completed."""
        await vote_repository.save(sample_vote_session)

        # Complete the session
        await vote_repository.complete_session(123, VoteType.SKIP, result="passed")

        # Session should no longer be active (completed_at is set)
        active = await vote_repository.get(123, VoteType.SKIP)
        assert active is None

    async def test_complete_session_for_nonexistent(self, vote_repository):
        """Should handle completing non-existent session gracefully."""
        # Complete_session doesn't return a value, just verify it doesn't raise
        await vote_repository.complete_session(999, VoteType.SKIP, result="failed")

        # Verify no session exists
        session = await vote_repository.get(999, VoteType.SKIP)
        assert session is None

    async def test_add_vote_to_session(self, vote_repository, sample_vote_session):
        """Should add vote to existing session."""
        await vote_repository.save(sample_vote_session)

        # Add a vote
        sample_vote_session.add_vote(user_id=111)
        await vote_repository.save(sample_vote_session)

        # Retrieve and verify
        retrieved = await vote_repository.get(123, VoteType.SKIP)
        assert retrieved is not None
        assert 111 in retrieved.voters

    async def test_multiple_votes_persist(self, vote_repository, sample_vote_session):
        """Should persist multiple votes for a session."""
        await vote_repository.save(sample_vote_session)

        # Add multiple votes
        sample_vote_session.add_vote(111)
        sample_vote_session.add_vote(222)
        sample_vote_session.add_vote(333)
        await vote_repository.save(sample_vote_session)

        # Retrieve and verify
        retrieved = await vote_repository.get(123, VoteType.SKIP)
        assert retrieved is not None
        assert len(retrieved.voters) == 3
        assert all(user_id in retrieved.voters for user_id in [111, 222, 333])

    async def test_delete_for_guild_removes_all_sessions(self, vote_repository):
        """Should delete all vote sessions for a guild."""
        guild_id = 123

        # Create multiple sessions for the guild
        session1 = VoteSession(
            guild_id=guild_id,
            track_id="track_1",
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC),
        )
        session2 = VoteSession(
            guild_id=guild_id,
            track_id="track_2",
            vote_type=VoteType.STOP,
            threshold=2,
            started_at=datetime.now(UTC),
        )

        await vote_repository.save(session1)
        await vote_repository.save(session2)

        # Delete all sessions for guild
        count = await vote_repository.delete_for_guild(guild_id)

        assert count == 2

        # Verify both are gone
        assert await vote_repository.get(guild_id, VoteType.SKIP) is None
        assert await vote_repository.get(guild_id, VoteType.STOP) is None

    async def test_delete_for_guild_returns_zero_when_empty(self, vote_repository):
        """Should return 0 when no sessions exist for guild."""
        count = await vote_repository.delete_for_guild(999)

        assert count == 0
