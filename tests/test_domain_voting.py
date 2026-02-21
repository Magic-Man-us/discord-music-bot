"""
Unit Tests for Domain Voting Layer

Tests for:
- Value Objects: VoteType, VoteResult
- Entities: Vote, VoteSession
- Services: VotingDomainService, VoteResultHandler
"""

from datetime import UTC, datetime, timedelta

import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.voting.entities import Vote, VoteSession
from discord_music_player.domain.voting.services import VoteResultHandler, VotingDomainService
from discord_music_player.domain.voting.value_objects import VoteResult, VoteType

# =============================================================================
# VoteType Value Object Tests
# =============================================================================


class TestVoteType:
    """Unit tests for VoteType enum value object."""

    def test_vote_types_exist(self):
        """Should have SKIP, STOP, and CLEAR types."""
        assert VoteType.SKIP.value == "skip"
        assert VoteType.STOP.value == "stop"
        assert VoteType.CLEAR.value == "clear"

    def test_past_tense_property(self):
        """Should return correct past tense forms."""
        assert VoteType.SKIP.past_tense == "skipped"
        assert VoteType.STOP.past_tense == "stopped"
        assert VoteType.CLEAR.past_tense == "cleared"

    def test_action_verb_property(self):
        """Should return correct action verbs."""
        assert VoteType.SKIP.action_verb == "skip"
        assert VoteType.STOP.action_verb == "stop"
        assert VoteType.CLEAR.action_verb == "clear"


# =============================================================================
# VoteResult Value Object Tests
# =============================================================================


class TestVoteResult:
    """Unit tests for VoteResult enum value object."""

    def test_success_results(self):
        """is_success should be True for successful outcomes."""
        assert VoteResult.VOTE_RECORDED.is_success is True
        assert VoteResult.THRESHOLD_MET.is_success is True
        assert VoteResult.REQUESTER_SKIP.is_success is True
        assert VoteResult.AUTO_SKIP.is_success is True

    def test_failure_results(self):
        """is_success should be False for failure outcomes."""
        assert VoteResult.ALREADY_VOTED.is_success is False
        assert VoteResult.NO_PLAYING.is_success is False
        assert VoteResult.NOT_IN_CHANNEL.is_success is False
        assert VoteResult.BOT_NOT_IN_CHANNEL.is_success is False
        assert VoteResult.VOTE_EXPIRED.is_success is False
        assert VoteResult.INVALID_VOTE.is_success is False

    def test_action_executed_results(self):
        """action_executed should be True when action was performed."""
        assert VoteResult.THRESHOLD_MET.action_executed is True
        assert VoteResult.REQUESTER_SKIP.action_executed is True
        assert VoteResult.AUTO_SKIP.action_executed is True

    def test_action_not_executed_results(self):
        """action_executed should be False when action was not performed."""
        assert VoteResult.VOTE_RECORDED.action_executed is False
        assert VoteResult.ALREADY_VOTED.action_executed is False
        assert VoteResult.NOT_IN_CHANNEL.action_executed is False

    def test_get_message_vote_recorded(self):
        """Should return progress message for VOTE_RECORDED."""
        msg = VoteResult.VOTE_RECORDED.get_message(VoteType.SKIP, votes=2, needed=3)
        assert "2/3" in msg
        assert "skip" in msg

    def test_get_message_threshold_met(self):
        """Should return success message for THRESHOLD_MET."""
        msg = VoteResult.THRESHOLD_MET.get_message(VoteType.SKIP)
        assert "threshold met" in msg.lower()
        assert "skipped" in msg

    def test_get_message_requester_skip(self):
        """Should return requester message for REQUESTER_SKIP."""
        msg = VoteResult.REQUESTER_SKIP.get_message(VoteType.SKIP)
        assert "requester" in msg.lower()

    def test_get_message_already_voted(self):
        """Should return already voted message."""
        msg = VoteResult.ALREADY_VOTED.get_message(VoteType.SKIP)
        assert "already voted" in msg.lower()

    def test_get_message_not_in_channel(self):
        """Should return channel message for NOT_IN_CHANNEL."""
        msg = VoteResult.NOT_IN_CHANNEL.get_message(VoteType.SKIP)
        assert "voice channel" in msg.lower()


# =============================================================================
# Vote Entity Tests
# =============================================================================


class TestVote:
    """Unit tests for Vote entity."""

    def test_create_vote(self):
        """Should create vote with user_id and vote_type."""
        vote = Vote(user_id=12345, vote_type=VoteType.SKIP)
        assert vote.user_id == 12345
        assert vote.vote_type == VoteType.SKIP
        assert vote.timestamp is not None

    def test_vote_hashable(self):
        """Votes should be usable in sets."""
        vote1 = Vote(user_id=12345, vote_type=VoteType.SKIP)
        vote2 = Vote(user_id=12345, vote_type=VoteType.SKIP)
        vote3 = Vote(user_id=99999, vote_type=VoteType.SKIP)

        vote_set = {vote1, vote2, vote3}
        # vote1 and vote2 have same user_id and vote_type, so they're equal
        assert len(vote_set) == 2

    def test_vote_equality(self):
        """Votes with same user_id and vote_type should be equal."""
        vote1 = Vote(user_id=12345, vote_type=VoteType.SKIP)
        vote2 = Vote(user_id=12345, vote_type=VoteType.SKIP)
        vote3 = Vote(user_id=12345, vote_type=VoteType.STOP)

        assert vote1 == vote2
        assert vote1 != vote3

    def test_vote_equality_with_non_vote(self):
        """Vote equality with non-Vote object should return NotImplemented."""
        vote = Vote(user_id=12345, vote_type=VoteType.SKIP)
        assert vote.__eq__("not a vote") == NotImplemented


# =============================================================================
# VoteSession Entity Tests
# =============================================================================


class TestVoteSession:
    """Unit tests for VoteSession aggregate."""

    @pytest.fixture
    def session(self):
        """Fixture providing a fresh vote session."""
        return VoteSession(
            guild_id=123456789,
            track_id=TrackId("track123"),
            vote_type=VoteType.SKIP,
            threshold=3,
        )

    def test_create_session(self, session):
        """Should create session with correct initial state."""
        assert session.guild_id == 123456789
        assert session.track_id == TrackId("track123")
        assert session.vote_type == VoteType.SKIP
        assert session.threshold == 3
        assert session.vote_count == 0
        assert session.expires_at is not None

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        with pytest.raises(ValueError):
            VoteSession(
                guild_id=0,
                track_id=TrackId("track123"),
                vote_type=VoteType.SKIP,
                threshold=3,
            )

    def test_invalid_threshold_raises_error(self):
        """Should raise ValueError for threshold < 1."""
        with pytest.raises(ValueError):
            VoteSession(
                guild_id=123,
                track_id=TrackId("track123"),
                vote_type=VoteType.SKIP,
                threshold=0,
            )

    def test_vote_count_property(self, session):
        """vote_count should return number of voters."""
        assert session.vote_count == 0
        session.add_vote(111)
        assert session.vote_count == 1
        session.add_vote(222)
        assert session.vote_count == 2

    def test_votes_needed_property(self, session):
        """votes_needed should return remaining votes to threshold."""
        assert session.votes_needed == 3
        session.add_vote(111)
        assert session.votes_needed == 2
        session.add_vote(222)
        session.add_vote(333)
        assert session.votes_needed == 0

    def test_is_threshold_met_property(self, session):
        """is_threshold_met should be True when votes >= threshold."""
        assert session.is_threshold_met is False
        session.add_vote(111)
        session.add_vote(222)
        assert session.is_threshold_met is False
        session.add_vote(333)
        assert session.is_threshold_met is True

    def test_is_expired_property_not_expired(self, session):
        """is_expired should be False before expiration."""
        assert session.is_expired is False

    def test_is_expired_property_expired(self):
        """is_expired should be True after expiration."""
        session = VoteSession(
            guild_id=123456789,
            track_id=TrackId("track123"),
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        assert session.is_expired is True

    def test_voters_returns_frozen_set(self, session):
        """voters property should return immutable frozenset."""
        session.add_vote(111)
        session.add_vote(222)

        voters = session.voters
        assert isinstance(voters, frozenset)
        assert 111 in voters
        assert 222 in voters

    def test_add_vote_success(self, session):
        """add_vote should add voter and return threshold status."""
        result = session.add_vote(111)
        assert result is False  # Threshold not yet met
        assert session.has_voted(111) is True

    def test_add_vote_meets_threshold(self, session):
        """add_vote should return True when threshold met."""
        session.add_vote(111)
        session.add_vote(222)
        result = session.add_vote(333)
        assert result is True  # Threshold met

    def test_add_vote_duplicate_returns_false(self, session):
        """add_vote should return False for duplicate votes."""
        session.add_vote(111)
        result = session.add_vote(111)
        assert result is False
        assert session.vote_count == 1  # Not counted twice

    def test_remove_vote_success(self, session):
        """remove_vote should remove voter and return True."""
        session.add_vote(111)
        result = session.remove_vote(111)
        assert result is True
        assert session.has_voted(111) is False

    def test_remove_vote_not_voted(self, session):
        """remove_vote should return False if user hasn't voted."""
        result = session.remove_vote(999)
        assert result is False

    def test_has_voted(self, session):
        """has_voted should check if user has voted."""
        assert session.has_voted(111) is False
        session.add_vote(111)
        assert session.has_voted(111) is True

    def test_reset_clears_votes(self, session):
        """reset should clear all votes and reset timestamps."""
        session.add_vote(111)
        session.add_vote(222)
        original_started = session.started_at

        import time

        time.sleep(0.01)  # Small delay
        session.reset()

        assert session.vote_count == 0
        assert session.started_at > original_started

    def test_reset_with_new_track_id(self, session):
        """reset should update track_id when provided."""
        session.reset(new_track_id=TrackId("new_track"))
        assert session.track_id == TrackId("new_track")

    def test_extend_expiration(self, session):
        """extend_expiration should update expires_at."""
        original_expires = session.expires_at
        session.extend_expiration(minutes=10)
        assert session.expires_at > original_expires

    def test_update_threshold(self, session):
        """update_threshold should change threshold."""
        session.update_threshold(5)
        assert session.threshold == 5

    def test_update_threshold_invalid(self, session):
        """update_threshold should reject threshold < 1."""
        with pytest.raises(ValueError, match="Threshold must be at least 1"):
            session.update_threshold(0)

    def test_get_progress_string(self, session):
        """get_progress_string should return formatted progress."""
        session.add_vote(111)
        progress = session.get_progress_string()
        assert progress == "1/3 votes"

    def test_create_skip_session_factory(self):
        """create_skip_session should create properly configured session."""
        session = VoteSession.create_skip_session(
            guild_id=123456, track_id=TrackId("track789"), listener_count=6
        )
        assert session.guild_id == 123456
        assert session.track_id == TrackId("track789")
        assert session.vote_type == VoteType.SKIP
        # With 6 listeners: (6 // 2) + 1 = 4 threshold
        assert session.threshold == 4


# =============================================================================
# VotingDomainService Tests
# =============================================================================


class TestVotingDomainService:
    """Unit tests for VotingDomainService."""

    @pytest.fixture
    def track(self):
        """Fixture providing a sample track."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            requested_by_id=12345,
            requested_by_name="TestUser",
        )

    @pytest.fixture
    def session(self):
        """Fixture providing a fresh vote session."""
        return VoteSession(
            guild_id=123456789,
            track_id=TrackId("test123"),
            vote_type=VoteType.SKIP,
            threshold=3,
        )

    # --- calculate_threshold tests ---

    def test_calculate_threshold_zero_listeners(self):
        """Should return minimum threshold for 0 listeners."""
        threshold = VotingDomainService.calculate_threshold(0)
        assert threshold == 1

    def test_calculate_threshold_negative_listeners(self):
        """Should return minimum threshold for negative listeners."""
        threshold = VotingDomainService.calculate_threshold(-5)
        assert threshold == 1

    def test_calculate_threshold_one_listener(self):
        """Should return 1 for single listener."""
        threshold = VotingDomainService.calculate_threshold(1)
        assert threshold == 1

    def test_calculate_threshold_two_listeners(self):
        """Should return 2 for two listeners (majority)."""
        threshold = VotingDomainService.calculate_threshold(2)
        assert threshold == 2

    def test_calculate_threshold_three_listeners(self):
        """Should return 2 for three listeners (3//2 + 1 = 2)."""
        threshold = VotingDomainService.calculate_threshold(3)
        assert threshold == 2

    def test_calculate_threshold_ten_listeners(self):
        """Should return 6 for ten listeners (10//2 + 1 = 6)."""
        threshold = VotingDomainService.calculate_threshold(10)
        assert threshold == 6

    # --- can_auto_skip tests ---

    def test_can_auto_skip_requester(self, track):
        """Requester can always auto-skip their own track."""
        result = VotingDomainService.can_auto_skip(
            user_id=12345,
            track=track,
            listener_count=10,  # Same as requested_by_id
        )
        assert result is True

    def test_can_auto_skip_small_audience_one(self, track):
        """Anyone can skip with 1 listener."""
        result = VotingDomainService.can_auto_skip(
            user_id=99999,  # Different user
            track=track,
            listener_count=1,
        )
        assert result is True

    def test_can_auto_skip_small_audience_two(self, track):
        """Anyone can skip with 2 listeners."""
        result = VotingDomainService.can_auto_skip(
            user_id=99999,  # Different user
            track=track,
            listener_count=2,
        )
        assert result is True

    def test_cannot_auto_skip_large_audience(self, track):
        """Non-requester cannot auto-skip with large audience."""
        result = VotingDomainService.can_auto_skip(
            user_id=99999,  # Different user
            track=track,
            listener_count=5,
        )
        assert result is False

    # --- evaluate_vote tests ---

    def test_evaluate_vote_not_in_channel(self, session, track):
        """Should return NOT_IN_CHANNEL when user not in voice channel."""
        result, _ = VotingDomainService.evaluate_vote(
            session=session,
            user_id=99999,
            track=track,
            listener_count=5,
            user_in_channel=False,
        )
        assert result == VoteResult.NOT_IN_CHANNEL

    def test_evaluate_vote_expired_session(self, track):
        """Should return VOTE_EXPIRED for expired session."""
        expired_session = VoteSession(
            guild_id=123456789,
            track_id=TrackId("test123"),
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        result, _ = VotingDomainService.evaluate_vote(
            session=expired_session,
            user_id=99999,
            track=track,
            listener_count=5,
            user_in_channel=True,
        )
        assert result == VoteResult.VOTE_EXPIRED

    def test_evaluate_vote_requester_skip(self, session, track):
        """Should return REQUESTER_SKIP when requester votes."""
        result, _ = VotingDomainService.evaluate_vote(
            session=session,
            user_id=12345,  # Same as track's requested_by_id
            track=track,
            listener_count=5,
            user_in_channel=True,
        )
        assert result == VoteResult.REQUESTER_SKIP

    def test_evaluate_vote_auto_skip_small_audience(self, session, track):
        """Should return AUTO_SKIP for small audience."""
        result, _ = VotingDomainService.evaluate_vote(
            session=session,
            user_id=99999,  # Different user
            track=track,
            listener_count=2,  # Small audience
            user_in_channel=True,
        )
        assert result == VoteResult.AUTO_SKIP

    def test_evaluate_vote_already_voted(self, session, track):
        """Should return ALREADY_VOTED for duplicate votes."""
        session.add_vote(99999)
        result, _ = VotingDomainService.evaluate_vote(
            session=session,
            user_id=99999,
            track=track,
            listener_count=5,
            user_in_channel=True,
        )
        assert result == VoteResult.ALREADY_VOTED

    def test_evaluate_vote_recorded(self, session, track):
        """Should return VOTE_RECORDED for valid vote."""
        result, updated_session = VotingDomainService.evaluate_vote(
            session=session,
            user_id=99999,
            track=track,
            listener_count=5,
            user_in_channel=True,
        )
        assert result == VoteResult.VOTE_RECORDED
        assert updated_session.has_voted(99999)

    def test_evaluate_vote_threshold_met(self, session, track):
        """Should return THRESHOLD_MET when vote reaches threshold."""
        session.add_vote(111)
        session.add_vote(222)
        # Now one more vote will meet threshold of 3
        result, _ = VotingDomainService.evaluate_vote(
            session=session,
            user_id=333,
            track=track,
            listener_count=5,
            user_in_channel=True,
        )
        assert result == VoteResult.THRESHOLD_MET

    # --- should_reset_session tests ---

    def test_should_reset_session_different_track(self, session):
        """Should reset when track ID changes."""
        result = VotingDomainService.should_reset_session(
            session=session, current_track_id=TrackId("different_track")
        )
        assert result is True

    def test_should_reset_session_same_track(self, session):
        """Should not reset when track ID is same."""
        result = VotingDomainService.should_reset_session(
            session=session, current_track_id=TrackId("test123")
        )
        assert result is False

    def test_should_reset_session_expired(self):
        """Should reset when session is expired."""
        expired_session = VoteSession(
            guild_id=123456789,
            track_id=TrackId("test123"),
            vote_type=VoteType.SKIP,
            threshold=3,
            started_at=datetime.now(UTC) - timedelta(minutes=10),
            expires_at=datetime.now(UTC) - timedelta(minutes=5),
        )
        result = VotingDomainService.should_reset_session(
            session=expired_session, current_track_id=TrackId("test123")
        )
        assert result is True

    # --- create_response_message tests ---

    def test_create_response_message(self, session):
        """Should create formatted response message."""
        session.add_vote(111)
        msg = VotingDomainService.create_response_message(
            result=VoteResult.VOTE_RECORDED, session=session
        )
        assert "1/3" in msg


# =============================================================================
# VoteResultHandler Tests
# =============================================================================


class TestVoteResultHandler:
    """Unit tests for VoteResultHandler."""

    def test_should_execute_action_true(self):
        """should_execute_action should be True for action results."""
        assert VoteResultHandler.should_execute_action(VoteResult.THRESHOLD_MET) is True
        assert VoteResultHandler.should_execute_action(VoteResult.REQUESTER_SKIP) is True
        assert VoteResultHandler.should_execute_action(VoteResult.AUTO_SKIP) is True

    def test_should_execute_action_false(self):
        """should_execute_action should be False for non-action results."""
        assert VoteResultHandler.should_execute_action(VoteResult.VOTE_RECORDED) is False
        assert VoteResultHandler.should_execute_action(VoteResult.ALREADY_VOTED) is False

    def test_should_notify_progress_true(self):
        """should_notify_progress should be True for VOTE_RECORDED."""
        assert VoteResultHandler.should_notify_progress(VoteResult.VOTE_RECORDED) is True

    def test_should_notify_progress_false(self):
        """should_notify_progress should be False for other results."""
        assert VoteResultHandler.should_notify_progress(VoteResult.THRESHOLD_MET) is False
        assert VoteResultHandler.should_notify_progress(VoteResult.ALREADY_VOTED) is False

    def test_should_notify_failure_true(self):
        """should_notify_failure should be True for failure results."""
        assert VoteResultHandler.should_notify_failure(VoteResult.ALREADY_VOTED) is True
        assert VoteResultHandler.should_notify_failure(VoteResult.NOT_IN_CHANNEL) is True
        assert VoteResultHandler.should_notify_failure(VoteResult.BOT_NOT_IN_CHANNEL) is True
        assert VoteResultHandler.should_notify_failure(VoteResult.NO_PLAYING) is True
        assert VoteResultHandler.should_notify_failure(VoteResult.VOTE_EXPIRED) is True

    def test_should_notify_failure_false(self):
        """should_notify_failure should be False for success results."""
        assert VoteResultHandler.should_notify_failure(VoteResult.VOTE_RECORDED) is False
        assert VoteResultHandler.should_notify_failure(VoteResult.THRESHOLD_MET) is False
