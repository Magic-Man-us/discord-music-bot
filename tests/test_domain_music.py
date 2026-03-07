"""
Unit Tests for Domain Music Layer

Tests for:
- Value Objects: TrackId, QueuePosition, PlaybackState, LoopMode
- Entities: Track, GuildPlaybackSession
"""

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import (
    LoopMode,
    PlaybackState,
    QueuePosition,
    TrackId,
)
from discord_music_player.domain.shared.exceptions import (
    BusinessRuleViolationError,
    InvalidOperationError,
)

# =============================================================================
# TrackId Value Object Tests
# =============================================================================


class TestTrackId:
    """Unit tests for TrackId value object."""

    def test_create_valid_track_id(self):
        """Should create TrackId with valid value."""
        track_id = TrackId("dQw4w9WgXcQ")
        assert track_id.value == "dQw4w9WgXcQ"
        assert str(track_id) == "dQw4w9WgXcQ"

    def test_create_empty_raises_error(self):
        """Should raise ValueError for empty track ID."""
        with pytest.raises(ValueError):
            TrackId("")

    def test_create_whitespace_raises_error(self):
        """Should raise ValueError for whitespace-only track ID."""
        with pytest.raises(ValueError):
            TrackId("   ")

    def test_track_id_hashable(self):
        """Should be usable in sets and as dict keys."""
        id1 = TrackId("abc123")
        id2 = TrackId("abc123")
        id3 = TrackId("xyz789")

        # Same value should have same hash
        assert hash(id1) == hash(id2)

        # Can be used in sets
        id_set = {id1, id2, id3}
        assert len(id_set) == 2  # id1 and id2 are equal

    def test_from_youtube_watch_url(self):
        """Should extract video ID from youtube.com/watch URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        track_id = TrackId.from_url(url)
        assert track_id.value == "dQw4w9WgXcQ"

    def test_from_youtu_be_url(self):
        """Should extract video ID from youtu.be short URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        track_id = TrackId.from_url(url)
        assert track_id.value == "dQw4w9WgXcQ"

    def test_from_youtube_embed_url(self):
        """Should extract video ID from youtube.com/embed URL."""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        track_id = TrackId.from_url(url)
        assert track_id.value == "dQw4w9WgXcQ"

    def test_from_youtube_shorts_url(self):
        """Should extract video ID from youtube.com/shorts URL."""
        url = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
        track_id = TrackId.from_url(url)
        assert track_id.value == "dQw4w9WgXcQ"

    def test_from_non_youtube_url_uses_hash(self):
        """Should use URL hash for non-YouTube URLs."""
        url = "https://soundcloud.com/artist/track"
        track_id = TrackId.from_url(url)
        # Should be a 16-character hex string (MD5 hash truncated)
        assert len(track_id.value) == 16
        assert all(c in "0123456789abcdef" for c in track_id.value)


# =============================================================================
# QueuePosition Value Object Tests
# =============================================================================


class TestQueuePosition:
    """Unit tests for QueuePosition value object."""

    def test_create_valid_position(self):
        """Should create QueuePosition with valid value."""
        pos = QueuePosition(5)
        assert pos.value == 5
        assert str(pos) == "5"
        assert int(pos) == 5

    def test_create_zero_position(self):
        """Should allow position 0 (front of queue)."""
        pos = QueuePosition(0)
        assert pos.value == 0

    def test_negative_position_raises_error(self):
        """Should raise ValueError for negative position."""
        with pytest.raises(ValueError):
            QueuePosition(-1)

    def test_next_position(self):
        """Should return next position."""
        pos = QueuePosition(3)
        next_pos = pos.next()
        assert next_pos.value == 4

    def test_previous_position(self):
        """Should return previous position."""
        pos = QueuePosition(3)
        prev_pos = pos.previous()
        assert prev_pos.value == 2

    def test_previous_from_zero_stays_zero(self):
        """Should not go below 0 when getting previous."""
        pos = QueuePosition(0)
        prev_pos = pos.previous()
        assert prev_pos.value == 0


# =============================================================================
# PlaybackState Value Object Tests
# =============================================================================


class TestPlaybackState:
    """Unit tests for PlaybackState enum value object."""

    def test_valid_transitions_from_idle(self):
        """IDLE can only transition to PLAYING."""
        assert PlaybackState.IDLE.can_transition_to(PlaybackState.PLAYING) is True
        assert PlaybackState.IDLE.can_transition_to(PlaybackState.PAUSED) is False
        assert PlaybackState.IDLE.can_transition_to(PlaybackState.STOPPED) is False

    def test_valid_transitions_from_playing(self):
        """PLAYING can transition to PAUSED, STOPPED, or IDLE."""
        assert PlaybackState.PLAYING.can_transition_to(PlaybackState.PAUSED) is True
        assert PlaybackState.PLAYING.can_transition_to(PlaybackState.STOPPED) is True
        assert PlaybackState.PLAYING.can_transition_to(PlaybackState.IDLE) is True

    def test_valid_transitions_from_paused(self):
        """PAUSED can transition to PLAYING, STOPPED, or IDLE."""
        assert PlaybackState.PAUSED.can_transition_to(PlaybackState.PLAYING) is True
        assert PlaybackState.PAUSED.can_transition_to(PlaybackState.STOPPED) is True
        assert PlaybackState.PAUSED.can_transition_to(PlaybackState.IDLE) is True

    def test_valid_transitions_from_stopped(self):
        """STOPPED can transition to IDLE or PLAYING."""
        assert PlaybackState.STOPPED.can_transition_to(PlaybackState.IDLE) is True
        assert PlaybackState.STOPPED.can_transition_to(PlaybackState.PLAYING) is True
        assert PlaybackState.STOPPED.can_transition_to(PlaybackState.PAUSED) is False

    def test_is_active_property(self):
        """is_active should be True for PLAYING and PAUSED."""
        assert PlaybackState.PLAYING.is_active is True
        assert PlaybackState.PAUSED.is_active is True
        assert PlaybackState.IDLE.is_active is False
        assert PlaybackState.STOPPED.is_active is False

    def test_is_playing_property(self):
        """is_playing should only be True for PLAYING."""
        assert PlaybackState.PLAYING.is_playing is True
        assert PlaybackState.PAUSED.is_playing is False
        assert PlaybackState.IDLE.is_playing is False
        assert PlaybackState.STOPPED.is_playing is False

    def test_can_accept_commands_property(self):
        """can_accept_commands should be False only for STOPPED."""
        assert PlaybackState.PLAYING.can_accept_commands is True
        assert PlaybackState.PAUSED.can_accept_commands is True
        assert PlaybackState.IDLE.can_accept_commands is True
        assert PlaybackState.STOPPED.can_accept_commands is False


# =============================================================================
# LoopMode Value Object Tests
# =============================================================================


class TestLoopMode:
    """Unit tests for LoopMode enum value object."""

    def test_loop_modes_exist(self):
        """Should have OFF, TRACK, and QUEUE modes."""
        assert LoopMode.OFF.value == "off"
        assert LoopMode.TRACK.value == "track"
        assert LoopMode.QUEUE.value == "queue"

    def test_next_mode_cycles_correctly(self):
        """next_mode should cycle: OFF -> TRACK -> QUEUE -> OFF."""
        assert LoopMode.OFF.next_mode() == LoopMode.TRACK
        assert LoopMode.TRACK.next_mode() == LoopMode.QUEUE
        assert LoopMode.QUEUE.next_mode() == LoopMode.OFF


# =============================================================================
# Track Entity Tests
# =============================================================================


class TestTrack:
    """Unit tests for Track domain entity."""

    @pytest.fixture
    def valid_track_data(self):
        """Fixture providing valid track data."""
        return {
            "id": TrackId("abc123"),
            "title": "Test Song",
            "webpage_url": "https://youtube.com/watch?v=abc123",
        }

    def test_create_minimal_track(self, valid_track_data):
        """Should create track with minimal required fields."""
        track = Track(**valid_track_data)
        assert track.title == "Test Song"
        assert track.webpage_url == "https://youtube.com/watch?v=abc123"
        assert track.stream_url is None
        assert track.duration_seconds is None

    def test_create_full_track(self, valid_track_data):
        """Should create track with all fields."""
        track = Track(
            **valid_track_data,
            stream_url="https://stream.example.com/audio",
            duration_seconds=180,
            thumbnail_url="https://img.example.com/thumb.jpg",
            requested_by_id=12345,
            requested_by_name="TestUser",
        )
        assert track.stream_url == "https://stream.example.com/audio"
        assert track.duration_seconds == 180
        assert track.thumbnail_url == "https://img.example.com/thumb.jpg"
        assert track.requested_by_id == 12345

    def test_empty_title_raises_error(self, valid_track_data):
        """Should raise ValueError for empty title."""
        valid_track_data["title"] = ""
        with pytest.raises(ValueError):
            Track(**valid_track_data)

    def test_empty_url_raises_error(self, valid_track_data):
        """Should raise ValueError for empty webpage URL."""
        valid_track_data["webpage_url"] = ""
        with pytest.raises(ValueError):
            Track(**valid_track_data)

    def test_duration_formatted_minutes_seconds(self, valid_track_data):
        """Should format duration as MM:SS for short tracks."""
        track = Track(**valid_track_data, duration_seconds=185)
        assert track.duration_formatted == "3:05"

    def test_duration_formatted_hours(self, valid_track_data):
        """Should format duration as HH:MM:SS for long tracks."""
        track = Track(**valid_track_data, duration_seconds=3725)  # 1:02:05
        assert track.duration_formatted == "1:02:05"

    def test_duration_formatted_unknown(self, valid_track_data):
        """Should return 'Unknown' when duration is None."""
        track = Track(**valid_track_data)
        assert track.duration_formatted == "Unknown"

    def test_display_title_with_duration(self, valid_track_data):
        """Should include duration in display title."""
        track = Track(**valid_track_data, duration_seconds=180)
        assert track.display_title == "Test Song [3:00]"

    def test_display_title_without_duration(self, valid_track_data):
        """Should return plain title when no duration."""
        track = Track(**valid_track_data)
        assert track.display_title == "Test Song"

    def test_with_requester_creates_new_track(self, valid_track_data):
        """with_requester should create a new Track instance."""
        original = Track(**valid_track_data)
        updated = original.with_requester(user_id=999, user_name="NewUser")

        # Original unchanged
        assert original.requested_by_id is None

        # New track has requester info
        assert updated.requested_by_id == 999
        assert updated.requested_by_name == "NewUser"
        assert updated.requested_at is not None

        # Preserves other fields
        assert updated.title == original.title
        assert updated.webpage_url == original.webpage_url

    def test_was_requested_by_matching_user(self, valid_track_data):
        """was_requested_by should return True for matching user."""
        track = Track(**valid_track_data, requested_by_id=12345)
        assert track.was_requested_by(12345) is True

    def test_was_requested_by_different_user(self, valid_track_data):
        """was_requested_by should return False for different user."""
        track = Track(**valid_track_data, requested_by_id=12345)
        assert track.was_requested_by(99999) is False

    def test_was_requested_by_no_requester(self, valid_track_data):
        """was_requested_by should return False when no requester set."""
        track = Track(**valid_track_data)
        assert track.was_requested_by(12345) is False


# =============================================================================
# GuildPlaybackSession Entity Tests
# =============================================================================


class TestGuildPlaybackSession:
    """Unit tests for GuildPlaybackSession aggregate root."""

    @pytest.fixture
    def session(self):
        """Fixture providing a fresh session."""
        return GuildPlaybackSession(guild_id=123456789)

    @pytest.fixture
    def sample_track(self):
        """Fixture providing a sample track."""
        return Track(
            id=TrackId("test123"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test123",
            duration_seconds=180,
        )

    @pytest.fixture
    def another_track(self):
        """Fixture providing another sample track."""
        return Track(
            id=TrackId("another456"),
            title="Another Track",
            webpage_url="https://youtube.com/watch?v=another456",
            duration_seconds=240,
        )

    def test_create_session(self, session):
        """Should create session with correct initial state."""
        assert session.guild_id == 123456789
        assert session.queue == []
        assert session.current_track is None
        assert session.state == PlaybackState.IDLE
        assert session.loop_mode == LoopMode.OFF
        assert session.version == 0

    def test_invalid_guild_id_raises_error(self):
        """Should raise ValueError for non-positive guild ID."""
        with pytest.raises(ValueError):
            GuildPlaybackSession(guild_id=0)

        with pytest.raises(ValueError):
            GuildPlaybackSession(guild_id=-1)

    def test_queue_length_property(self, session, sample_track):
        """queue_length should return correct count."""
        assert session.queue_length == 0
        session.enqueue(sample_track)
        assert session.queue_length == 1

    def test_is_playing_property(self, session):
        """is_playing should reflect PLAYING state."""
        assert session.is_playing is False
        session.state = PlaybackState.PLAYING
        assert session.is_playing is True

    def test_is_paused_property(self, session):
        """is_paused should reflect PAUSED state."""
        assert session.is_paused is False
        session.state = PlaybackState.PAUSED
        assert session.is_paused is True

    def test_is_idle_property(self, session):
        """is_idle should reflect IDLE state."""
        assert session.is_idle is True
        session.state = PlaybackState.PLAYING
        assert session.is_idle is False

    def test_has_tracks_with_queue(self, session, sample_track):
        """has_tracks should be True when queue has items."""
        assert session.has_tracks is False
        session.enqueue(sample_track)
        assert session.has_tracks is True

    def test_has_tracks_with_current(self, session, sample_track):
        """has_tracks should be True when current track exists."""
        assert session.has_tracks is False
        session.current_track = sample_track
        assert session.has_tracks is True

    def test_can_add_to_queue_within_limit(self, session):
        """can_add_to_queue should be True under limit."""
        assert session.can_add_to_queue is True

    def test_can_add_to_queue_at_limit(self, session, sample_track):
        """can_add_to_queue should be False at limit."""
        # Fill queue to max
        for i in range(GuildPlaybackSession.MAX_QUEUE_SIZE):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.queue.append(track)

        assert session.can_add_to_queue is False

    # --- Queue Operations ---

    def test_enqueue_adds_to_end(self, session, sample_track, another_track):
        """enqueue should add track to end of queue."""
        pos1 = session.enqueue(sample_track)
        pos2 = session.enqueue(another_track)

        assert pos1.value == 0
        assert pos2.value == 1
        assert session.queue[0] == sample_track
        assert session.queue[1] == another_track

    def test_enqueue_returns_position(self, session, sample_track):
        """enqueue should return QueuePosition."""
        position = session.enqueue(sample_track)
        assert isinstance(position, QueuePosition)
        assert position.value == 0

    def test_enqueue_when_full_raises_error(self, session, sample_track):
        """enqueue should raise BusinessRuleViolationError when queue is full."""
        # Fill queue to max
        for i in range(GuildPlaybackSession.MAX_QUEUE_SIZE):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.queue.append(track)

        with pytest.raises(BusinessRuleViolationError, match="Queue is full"):
            session.enqueue(sample_track)

    def test_enqueue_next_adds_to_front(self, session, sample_track, another_track):
        """enqueue_next should add track to front of queue."""
        session.enqueue(sample_track)
        pos = session.enqueue_next(another_track)

        assert pos.value == 0
        assert session.queue[0] == another_track
        assert session.queue[1] == sample_track

    def test_dequeue_removes_from_front(self, session, sample_track, another_track):
        """dequeue should remove and return first track."""
        session.enqueue(sample_track)
        session.enqueue(another_track)

        dequeued = session.dequeue()

        assert dequeued == sample_track
        assert session.queue_length == 1
        assert session.queue[0] == another_track

    def test_dequeue_empty_returns_none(self, session):
        """dequeue should return None when queue is empty."""
        assert session.dequeue() is None

    def test_peek_returns_first_without_removing(self, session, sample_track):
        """peek should return first track without removing it."""
        session.enqueue(sample_track)

        peeked = session.peek()

        assert peeked == sample_track
        assert session.queue_length == 1  # Still there

    def test_peek_empty_returns_none(self, session):
        """peek should return None when queue is empty."""
        assert session.peek() is None

    def test_remove_at_valid_position(self, session, sample_track, another_track):
        """remove_at should remove track at specified position."""
        session.enqueue(sample_track)
        session.enqueue(another_track)

        removed = session.remove_at(0)

        assert removed == sample_track
        assert session.queue_length == 1
        assert session.queue[0] == another_track

    def test_remove_at_invalid_position(self, session, sample_track):
        """remove_at should return None for invalid position."""
        session.enqueue(sample_track)

        assert session.remove_at(-1) is None
        assert session.remove_at(5) is None
        assert session.queue_length == 1  # Unchanged

    def test_clear_queue(self, session, sample_track, another_track):
        """clear_queue should remove all tracks and return count."""
        session.enqueue(sample_track)
        session.enqueue(another_track)

        count = session.clear_queue()

        assert count == 2
        assert session.queue_length == 0

    # --- State Transitions ---

    def test_transition_to_valid_state(self, session):
        """transition_to should change state for valid transition."""
        session.transition_to(PlaybackState.PLAYING)
        assert session.state == PlaybackState.PLAYING

    def test_transition_to_invalid_state_raises_error(self, session):
        """transition_to should raise InvalidOperationError for invalid transition."""
        with pytest.raises(InvalidOperationError, match="Cannot transition"):
            session.transition_to(PlaybackState.PAUSED)  # IDLE -> PAUSED is invalid

    def test_start_playback(self, session, sample_track):
        """start_playback should set current track and state."""
        session.start_playback(sample_track)

        assert session.current_track == sample_track
        assert session.state == PlaybackState.PLAYING

    def test_pause(self, session, sample_track):
        """pause should transition to PAUSED state."""
        session.start_playback(sample_track)
        session.pause()
        assert session.state == PlaybackState.PAUSED

    def test_resume(self, session, sample_track):
        """resume should transition from PAUSED to PLAYING."""
        session.start_playback(sample_track)
        session.pause()
        session.resume()
        assert session.state == PlaybackState.PLAYING

    def test_stop(self, session, sample_track):
        """stop should set state to STOPPED and clear current track."""
        session.start_playback(sample_track)
        session.stop()

        assert session.state == PlaybackState.STOPPED
        assert session.current_track is None

    def test_reset(self, session, sample_track, another_track):
        """reset should clear everything and return to IDLE."""
        session.enqueue(sample_track)
        session.start_playback(another_track)

        session.reset()

        assert session.state == PlaybackState.IDLE
        assert session.current_track is None
        assert session.queue_length == 0

    # --- Loop Mode ---

    def test_toggle_loop_cycles_modes(self, session):
        """toggle_loop should cycle through modes."""
        assert session.loop_mode == LoopMode.OFF

        result1 = session.toggle_loop()
        assert result1 == LoopMode.TRACK
        assert session.loop_mode == LoopMode.TRACK

        result2 = session.toggle_loop()
        assert result2 == LoopMode.QUEUE

        result3 = session.toggle_loop()
        assert result3 == LoopMode.OFF

    # --- Advance to Next Track ---

    def test_advance_with_loop_track_repeats(self, session, sample_track):
        """advance_to_next_track should repeat track in TRACK loop mode."""
        session.current_track = sample_track
        session.loop_mode = LoopMode.TRACK

        next_track = session.advance_to_next_track()

        assert next_track == sample_track

    def test_advance_with_loop_queue_requeues(self, session, sample_track, another_track):
        """advance_to_next_track should re-add current track in QUEUE loop mode."""
        session.current_track = sample_track
        session.enqueue(another_track)
        session.loop_mode = LoopMode.QUEUE

        next_track = session.advance_to_next_track()

        assert next_track == another_track
        assert session.queue[-1] == sample_track  # Re-added to end

    def test_advance_without_loop_clears_current(self, session, sample_track, another_track):
        """advance_to_next_track should move to next in queue without loop."""
        session.current_track = sample_track
        session.enqueue(another_track)

        next_track = session.advance_to_next_track()

        assert next_track == another_track
        assert session.current_track == another_track

    def test_advance_empty_queue_goes_idle(self, session, sample_track):
        """advance_to_next_track should go IDLE when queue empty."""
        session.current_track = sample_track
        session.state = PlaybackState.PLAYING

        next_track = session.advance_to_next_track()

        assert next_track is None
        assert session.state == PlaybackState.IDLE

    # --- Queue Manipulation ---

    def test_move_track_valid_positions(self, session):
        """move_track should reorder tracks correctly."""
        tracks = []
        for i in range(3):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            tracks.append(track)
            session.enqueue(track)

        result = session.move_track(from_pos=0, to_pos=2)

        assert result is True
        assert session.queue[0] == tracks[1]
        assert session.queue[1] == tracks[2]
        assert session.queue[2] == tracks[0]

    def test_move_track_invalid_positions(self, session, sample_track):
        """move_track should return False for invalid positions."""
        session.enqueue(sample_track)

        assert session.move_track(from_pos=-1, to_pos=0) is False
        assert session.move_track(from_pos=0, to_pos=5) is False
        assert session.move_track(from_pos=5, to_pos=0) is False

    def test_shuffle_randomizes_queue(self, session):
        """shuffle should reorder queue (statistically)."""
        # Add many tracks
        for i in range(20):
            track = Track(
                id=TrackId(f"track{i}"),
                title=f"Track {i}",
                webpage_url=f"https://youtube.com/watch?v=track{i}",
            )
            session.enqueue(track)

        original_order = [t.id.value for t in session.queue]
        session.shuffle()
        new_order = [t.id.value for t in session.queue]

        # With 20 items, extremely unlikely to stay in same order
        assert original_order != new_order
        # But should have same items
        assert sorted(original_order) == sorted(new_order)

    def test_touch_updates_last_activity(self, session):
        """touch should update last_activity timestamp."""
        original_time = session.last_activity

        import time

        time.sleep(0.01)  # Small delay to ensure time difference

        session.touch()

        assert session.last_activity > original_time
