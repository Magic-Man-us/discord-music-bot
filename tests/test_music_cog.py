"""
Comprehensive Unit Tests for MusicCog

Tests for all slash commands and functionality in the music cog:
- /play, /skip, /stop, /pause, /resume, /queue, /current, /clear
- /loop, /shuffle, /remove, /leave, /played
- Autocomplete handlers
- Permission checks and validation
- Discord interaction mocking
- Error handling
- Integration with container services
- Edge cases (empty queue, invalid positions, etc.)

Uses pytest with async/await patterns and proper mocking.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import PlaybackState, TrackId
from discord_music_player.domain.voting.value_objects import VoteResult
from discord_music_player.infrastructure.discord.cogs.music_cog import (
    MusicCog,
    _GuildMessageState,
    _TrackedMessage,
    _TrackKey,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.fetch_channel = AsyncMock(return_value=None)
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    container = MagicMock()

    # Mock playback service (mix of sync and async methods)
    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()
    container.playback_service.stop_playback = AsyncMock()
    container.playback_service.pause_playback = AsyncMock()
    container.playback_service.resume_playback = AsyncMock()
    container.playback_service.skip_track = AsyncMock()
    container.playback_service.cleanup_guild = AsyncMock()
    container.playback_service.set_track_finished_callback = MagicMock()  # SYNC method
    container.playback_service.set_volume = AsyncMock()

    # Mock queue service (async methods)
    container.queue_service = MagicMock()
    container.queue_service.enqueue = AsyncMock()
    container.queue_service.enqueue_next = AsyncMock()
    container.queue_service.get_queue = AsyncMock()
    container.queue_service.clear_queue = AsyncMock()
    container.queue_service.remove_track = AsyncMock()
    container.queue_service.move_track = AsyncMock()
    container.queue_service.shuffle_queue = AsyncMock()
    container.queue_service.toggle_loop = AsyncMock()

    # Mock audio resolver (async methods)
    container.audio_resolver = MagicMock()
    container.audio_resolver.resolve = AsyncMock()
    container.audio_resolver.search = AsyncMock()

    # Mock voice adapter (mix of sync and async methods)
    container.voice_adapter = MagicMock()
    container.voice_adapter.connect = AsyncMock()
    container.voice_adapter.disconnect = AsyncMock()
    container.voice_adapter.is_connected = MagicMock(return_value=False)  # SYNC method
    container.voice_adapter.play = AsyncMock()
    container.voice_adapter.pause = AsyncMock()
    container.voice_adapter.resume = AsyncMock()
    container.voice_adapter.stop = AsyncMock()

    # Mock repositories (async methods)
    container.session_repository = MagicMock()
    container.session_repository.get = AsyncMock()
    container.session_repository.save = AsyncMock()
    container.session_repository.delete = AsyncMock()

    container.history_repository = MagicMock()
    container.history_repository.record_play = AsyncMock()

    # Mock vote skip handler (async methods)
    container.vote_skip_handler = MagicMock()
    container.vote_skip_handler.execute = AsyncMock()

    # Mock warmup tracker (sync methods)
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0

    # Mock settings
    container.settings = MagicMock()
    container.settings.discord.owner_ids = [999999999]

    return container


@pytest.fixture
def music_cog(mock_bot, mock_container):
    """Create a MusicCog instance with mocked dependencies."""
    return MusicCog(mock_bot, mock_container)


@pytest.fixture
def mock_interaction():
    """Create a mock Discord Interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=123456))

    # Guild and user setup
    interaction.guild = MagicMock()
    interaction.guild.id = 111111111
    interaction.channel_id = 222222222

    # Member with voice state
    member = MagicMock(spec=discord.Member)
    member.id = 333333333
    member.display_name = "TestUser"
    member.name = "testuser"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 444444444
    member.guild_permissions = MagicMock()
    member.guild_permissions.administrator = False

    interaction.user = member

    return interaction


@pytest.fixture
def sample_track():
    """Create a sample track for testing."""
    return Track(
        id=TrackId("test123"),
        title="Test Song",
        webpage_url="https://youtube.com/watch?v=test123",
        stream_url="https://stream.example.com/test.mp3",
        duration_seconds=180,
        thumbnail_url="https://example.com/thumb.jpg",
        artist="Test Artist",
        uploader="Test Uploader",
        like_count=1000,
        requested_by_id=333333333,
        requested_by_name="TestUser",
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_session(sample_track):
    """Create a sample playback session."""
    session = GuildPlaybackSession(guild_id=111111111)
    session.current_track = sample_track
    session.state = PlaybackState.PLAYING
    return session


# =============================================================================
# Helper Classes Tests
# =============================================================================


class TestTrackKey:
    """Tests for _TrackKey helper class."""

    def test_from_track_creates_key(self, sample_track):
        """Should create track key from track."""
        key = _TrackKey.from_track(sample_track)

        assert key.track_id == "test123"
        assert key.requested_by_id == 333333333
        assert key.requested_at == sample_track.requested_at

    def test_track_keys_equal_for_same_track(self, sample_track):
        """Should create equal keys for same track."""
        key1 = _TrackKey.from_track(sample_track)
        key2 = _TrackKey.from_track(sample_track)

        assert key1 == key2

    def test_track_keys_frozen(self, sample_track):
        """Should be immutable (frozen)."""
        key = _TrackKey.from_track(sample_track)

        with pytest.raises(AttributeError):
            key.track_id = "modified"


class TestTrackedMessage:
    """Tests for _TrackedMessage helper class."""

    def test_from_track_creates_message(self, sample_track):
        """Should create tracked message from track."""
        msg = _TrackedMessage.from_track(sample_track, channel_id=123, message_id=456)

        assert msg.channel_id == 123
        assert msg.message_id == 456
        assert msg.track_key.track_id == "test123"


class TestGuildMessageState:
    """Tests for _GuildMessageState helper class."""

    def test_initial_state_empty(self):
        """Should start with no messages."""
        state = _GuildMessageState()

        assert state.now_playing is None
        assert len(state.queued) == 0

    def test_pop_matching_queued_finds_and_removes(self, sample_track):
        """Should find and remove matching queued message."""
        state = _GuildMessageState()
        msg = _TrackedMessage.from_track(sample_track, channel_id=1, message_id=2)
        state.queued.append(msg)

        found = state.pop_matching_queued(sample_track)

        assert found == msg
        assert len(state.queued) == 0

    def test_pop_matching_queued_returns_none_if_not_found(self, sample_track):
        """Should return None if track not found."""
        state = _GuildMessageState()

        found = state.pop_matching_queued(sample_track)

        assert found is None

    def test_pop_matching_queued_removes_only_matching(self, sample_track):
        """Should only remove the matching track."""
        state = _GuildMessageState()

        other_track = Track(
            id=TrackId("other"),
            title="Other",
            webpage_url="https://youtube.com/watch?v=other",
            requested_by_id=999,
        )

        msg1 = _TrackedMessage.from_track(sample_track, channel_id=1, message_id=1)
        msg2 = _TrackedMessage.from_track(other_track, channel_id=1, message_id=2)

        state.queued.append(msg1)
        state.queued.append(msg2)

        found = state.pop_matching_queued(sample_track)

        assert found == msg1
        assert len(state.queued) == 1
        assert state.queued[0] == msg2


# =============================================================================
# Cog Initialization Tests
# =============================================================================


class TestMusicCogInitialization:
    """Tests for MusicCog initialization and lifecycle."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        cog = MusicCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container
        assert len(cog._message_state_by_guild) == 0

    @pytest.mark.asyncio
    async def test_cog_load_registers_callback(self, music_cog, mock_container):
        """Should register track finished callback on load."""
        await music_cog.cog_load()

        mock_container.playback_service.set_track_finished_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_clears_message_state(self, music_cog, sample_track):
        """Should clear message state on unload."""
        # Add some state
        music_cog._message_state_by_guild[111] = _GuildMessageState()

        await music_cog.cog_unload()

        assert len(music_cog._message_state_by_guild) == 0

    def test_cleanup_guild_message_state(self, music_cog):
        """Should cleanup message state for specific guild."""
        music_cog._message_state_by_guild[111] = _GuildMessageState()
        music_cog._message_state_by_guild[222] = _GuildMessageState()

        music_cog.cleanup_guild_message_state(111)

        assert 111 not in music_cog._message_state_by_guild
        assert 222 in music_cog._message_state_by_guild


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for internal helper methods."""

    @pytest.mark.asyncio
    async def test_send_ephemeral_not_responded(self, music_cog, mock_interaction):
        """Should use response.send_message when not responded."""
        await music_cog._send_ephemeral(mock_interaction, "Test message")

        mock_interaction.response.send_message.assert_called_once_with(
            "Test message", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_send_ephemeral_already_responded(self, music_cog, mock_interaction):
        """Should use followup.send when already responded."""
        mock_interaction.response.is_done.return_value = True

        await music_cog._send_ephemeral(mock_interaction, "Test message")

        mock_interaction.followup.send.assert_called_once_with("Test message", ephemeral=True)

    @pytest.mark.asyncio
    async def test_get_member_success(self, music_cog, mock_interaction):
        """Should return member when valid."""
        member = await music_cog._get_member(mock_interaction)

        assert member == mock_interaction.user

    @pytest.mark.asyncio
    async def test_get_member_no_guild(self, music_cog, mock_interaction):
        """Should return None when no guild."""
        mock_interaction.guild = None

        member = await music_cog._get_member(mock_interaction)

        assert member is None
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_member_not_member(self, music_cog, mock_interaction):
        """Should return None when user is not a Member."""
        mock_interaction.user = MagicMock(spec=discord.User)  # Not a Member

        member = await music_cog._get_member(mock_interaction)

        assert member is None

    @pytest.mark.asyncio
    async def test_ensure_voice_warmup_passed(self, music_cog, mock_interaction, mock_container):
        """Should return True when warmup passed."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 0

        result = await music_cog._ensure_voice_warmup(mock_interaction, mock_interaction.user)

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_voice_warmup_required(self, music_cog, mock_interaction, mock_container):
        """Should return False and notify when warmup required."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 5

        result = await music_cog._ensure_voice_warmup(mock_interaction, mock_interaction.user)

        assert result is False
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_user_in_voice_and_warm_success(self, music_cog, mock_interaction):
        """Should return True when user in voice and warm."""
        result = await music_cog._ensure_user_in_voice_and_warm(mock_interaction)

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_user_in_voice_and_warm_not_in_voice(self, music_cog, mock_interaction):
        """Should return False when user not in voice."""
        mock_interaction.user.voice = None

        result = await music_cog._ensure_user_in_voice_and_warm(mock_interaction)

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_voice_connects_bot(self, music_cog, mock_interaction, mock_container):
        """Should connect bot to voice channel."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=True)

        result = await music_cog._ensure_voice(mock_interaction)

        assert result is True
        mock_container.voice_adapter.ensure_connected.assert_called_once_with(111111111, 444444444)

    @pytest.mark.asyncio
    async def test_ensure_voice_fails_to_connect(self, music_cog, mock_interaction, mock_container):
        """Should return False when cannot connect to voice."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=False)

        result = await music_cog._ensure_voice(mock_interaction)

        assert result is False

    def test_format_requester_with_id(self, music_cog, sample_track):
        """Should format requester with user mention."""
        result = music_cog._format_requester(sample_track)

        assert result == "<@333333333>"

    def test_format_requester_with_name_only(self, music_cog):
        """Should format requester with name when no ID."""
        track = Track(
            id=TrackId("test"),
            title="Test",
            webpage_url="https://example.com",
            requested_by_name="TestUser",
        )

        result = music_cog._format_requester(track)

        assert result == "TestUser"

    def test_format_requester_unknown(self, music_cog):
        """Should return Unknown when no requester info."""
        track = Track(
            id=TrackId("test"),
            title="Test",
            webpage_url="https://example.com",
        )

        result = music_cog._format_requester(track)

        assert result == "Unknown"

    def test_format_queued_line(self, music_cog, sample_track):
        """Should format queued message line."""
        result = music_cog._format_queued_line(sample_track)

        assert "⏭️" in result
        assert "Queued for play" in result
        assert sample_track.title in result
        assert "<@333333333>" in result

    def test_format_finished_line(self, music_cog, sample_track):
        """Should format finished message line."""
        result = music_cog._format_finished_line(sample_track)

        assert "✅" in result
        assert "Finished playing" in result
        assert sample_track.title in result

    def test_build_now_playing_embed(self, music_cog, sample_track):
        """Should build now playing embed."""
        embed = music_cog._build_now_playing_embed(sample_track)

        assert isinstance(embed, discord.Embed)
        assert embed.title == "🎵 Now Playing"
        assert sample_track.title in embed.description
        assert embed.thumbnail.url == sample_track.thumbnail_url
        assert len(embed.fields) == 3  # Duration, Artist, Likes

    def test_build_now_playing_embed_minimal_track(self, music_cog):
        """Should build embed for track with minimal info."""
        track = Track(
            id=TrackId("test"),
            title="Minimal Track",
            webpage_url="https://example.com",
        )

        embed = music_cog._build_now_playing_embed(track)

        assert isinstance(embed, discord.Embed)
        assert track.title in embed.description


# =============================================================================
# /play Command Tests
# =============================================================================


class TestPlayCommand:
    """Tests for /play command."""

    @pytest.mark.asyncio
    async def test_play_successful_enqueue(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should successfully enqueue and play track."""
        # Setup mocks
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.position = 0
        enqueue_result.should_start = True
        enqueue_result.track = sample_track
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await music_cog.play.callback(music_cog, mock_interaction, "test query")

        # Verify deferred
        mock_interaction.response.defer.assert_called_once()

        # Verify resolved
        mock_container.audio_resolver.resolve.assert_called_once_with("test query")

        # Verify enqueued
        mock_container.queue_service.enqueue.assert_called_once()

        # Verify started playback
        mock_container.playback_service.start_playback.assert_called_once_with(111111111)

    @pytest.mark.asyncio
    async def test_play_track_not_found(self, music_cog, mock_interaction, mock_container):
        """Should handle track not found."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=None)

        await music_cog.play.callback(music_cog, mock_interaction, "nonexistent track")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "Couldn't find" in args[0][0]

    @pytest.mark.asyncio
    async def test_play_voice_connection_failed(self, music_cog, mock_interaction, mock_container):
        """Should handle voice connection failure."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=False)
        mock_container.audio_resolver.resolve = AsyncMock()

        await music_cog.play.callback(music_cog, mock_interaction, "test query")

        # Should return early without resolving
        mock_container.audio_resolver.resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_enqueue_failed(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle enqueue failure."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)

        enqueue_result = MagicMock()
        enqueue_result.success = False
        enqueue_result.message = "Queue is full"
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await music_cog.play.callback(music_cog, mock_interaction, "test query")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "Queue is full" in args[0][0]

    @pytest.mark.asyncio
    async def test_play_queued_not_started(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should queue track without starting playback."""
        mock_container.voice_adapter.is_connected.return_value = True
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.position = 5
        enqueue_result.should_start = False
        enqueue_result.track = sample_track
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await music_cog.play.callback(music_cog, mock_interaction, "test query")

        # Should not start playback
        mock_container.playback_service.start_playback.assert_not_called()

        # Should send queued message
        mock_interaction.followup.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_exception_handling(self, music_cog, mock_interaction, mock_container):
        """Should handle exceptions gracefully."""
        mock_container.voice_adapter.is_connected.return_value = True
        mock_container.audio_resolver.resolve.side_effect = Exception("Network error")

        await music_cog.play.callback(music_cog, mock_interaction, "test query")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "error" in args[0][0].lower()


# =============================================================================
# /skip Command Tests
# =============================================================================


class TestSkipCommand:
    """Tests for /skip command."""

    @pytest.mark.asyncio
    async def test_skip_vote_skip_success(self, music_cog, mock_interaction, mock_container):
        """Should handle vote skip successfully."""
        # Mock the result directly without creating a frozen instance
        result = MagicMock()
        result.result = VoteResult.VOTE_RECORDED
        result.votes_current = 2
        result.votes_needed = 3
        result.action_executed = False
        mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)

        await music_cog.skip.callback(music_cog, mock_interaction, force=False)

        mock_container.vote_skip_handler.handle.assert_called_once()
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_threshold_met(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should skip when threshold met."""
        # Mock the result directly without creating a frozen instance
        result = MagicMock()
        result.result = VoteResult.THRESHOLD_MET
        result.votes_current = 3
        result.votes_needed = 3
        result.action_executed = True
        mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await music_cog.skip.callback(music_cog, mock_interaction, force=False)

        mock_container.playback_service.skip_track.assert_called_once_with(111111111)

    @pytest.mark.asyncio
    async def test_skip_force_by_admin(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should allow force skip by admin."""
        mock_interaction.user.guild_permissions.administrator = True
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await music_cog.skip.callback(music_cog, mock_interaction, force=True)

        mock_container.playback_service.skip_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_force_by_owner(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should allow force skip by owner."""
        mock_interaction.user.id = 999999999  # Owner ID
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await music_cog.skip.callback(music_cog, mock_interaction, force=True)

        mock_container.playback_service.skip_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_force_denied_for_regular_user(self, music_cog, mock_interaction):
        """Should deny force skip for regular user."""
        await music_cog.skip.callback(music_cog, mock_interaction, force=True)

        mock_interaction.response.send_message.assert_called_once()
        args = mock_interaction.response.send_message.call_args
        assert "administrator" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_skip_nothing_playing(self, music_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.skip_track = AsyncMock(return_value=None)
        mock_interaction.user.guild_permissions.administrator = True

        await music_cog.skip.callback(music_cog, mock_interaction, force=True)

        mock_interaction.response.send_message.assert_called_once()
        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /stop Command Tests
# =============================================================================


class TestStopCommand:
    """Tests for /stop command."""

    @pytest.mark.asyncio
    async def test_stop_success(self, music_cog, mock_interaction, mock_container):
        """Should stop playback and clear queue."""
        mock_container.playback_service.stop_playback = AsyncMock(return_value=True)
        mock_container.queue_service.clear = AsyncMock(return_value=5)

        await music_cog.stop.callback(music_cog, mock_interaction)

        mock_container.playback_service.stop_playback.assert_called_once_with(111111111)
        mock_container.queue_service.clear.assert_called_once_with(111111111)
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_nothing_playing(self, music_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.stop_playback = AsyncMock(return_value=False)
        mock_container.queue_service.clear = AsyncMock(return_value=0)

        await music_cog.stop.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /pause Command Tests
# =============================================================================


class TestPauseCommand:
    """Tests for /pause command."""

    @pytest.mark.asyncio
    async def test_pause_success(self, music_cog, mock_interaction, mock_container):
        """Should pause playback."""
        mock_container.playback_service.pause_playback = AsyncMock(return_value=True)

        await music_cog.pause.callback(music_cog, mock_interaction)

        mock_container.playback_service.pause_playback.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Paused" in args[0][0]

    @pytest.mark.asyncio
    async def test_pause_nothing_playing(self, music_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.pause_playback = AsyncMock(return_value=False)

        await music_cog.pause.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /resume Command Tests
# =============================================================================


class TestResumeCommand:
    """Tests for /resume command."""

    @pytest.mark.asyncio
    async def test_resume_success(self, music_cog, mock_interaction, mock_container):
        """Should resume playback."""
        mock_container.playback_service.resume_playback = AsyncMock(return_value=True)

        await music_cog.resume.callback(music_cog, mock_interaction)

        mock_container.playback_service.resume_playback.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Resumed" in args[0][0]

    @pytest.mark.asyncio
    async def test_resume_nothing_paused(self, music_cog, mock_interaction, mock_container):
        """Should handle nothing paused."""
        mock_container.playback_service.resume_playback = AsyncMock(return_value=False)

        await music_cog.resume.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /queue Command Tests
# =============================================================================


class TestQueueCommand:
    """Tests for /queue command."""

    @pytest.mark.asyncio
    async def test_queue_empty(self, music_cog, mock_interaction, mock_container):
        """Should handle empty queue."""
        queue_info = MagicMock()
        queue_info.total_tracks = 0
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.queue.callback(music_cog, mock_interaction, page=1)

        args = mock_interaction.response.send_message.call_args
        assert "empty" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_queue_with_tracks(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display queue with tracks."""
        queue_info = MagicMock()
        queue_info.total_tracks = 3
        queue_info.current_track = sample_track
        queue_info.tracks = [sample_track, sample_track, sample_track]
        queue_info.total_duration = 540
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.queue.callback(music_cog, mock_interaction, page=1)

        # Should send embed
        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs
        embed = call_args.kwargs["embed"]
        assert "Queue" in embed.title

    @pytest.mark.asyncio
    async def test_queue_pagination(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle pagination."""
        queue_info = MagicMock()
        queue_info.total_tracks = 25
        queue_info.current_track = None
        queue_info.tracks = [sample_track] * 25
        queue_info.total_duration = 4500
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.queue.callback(music_cog, mock_interaction, page=2)

        # Should work without error
        mock_interaction.response.send_message.assert_called_once()


# =============================================================================
# /current Command Tests
# =============================================================================


class TestCurrentCommand:
    """Tests for /current command."""

    @pytest.mark.asyncio
    async def test_current_with_track(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display current track."""
        queue_info = MagicMock()
        queue_info.current_track = sample_track
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.current.callback(music_cog, mock_interaction)

        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_current_nothing_playing(self, music_cog, mock_interaction, mock_container):
        """Should handle no current track."""
        queue_info = MagicMock()
        queue_info.current_track = None
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.current.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /shuffle Command Tests
# =============================================================================


class TestShuffleCommand:
    """Tests for /shuffle command."""

    @pytest.mark.asyncio
    async def test_shuffle_success(self, music_cog, mock_interaction, mock_container):
        """Should shuffle queue."""
        mock_container.queue_service.shuffle = AsyncMock(return_value=True)

        await music_cog.shuffle.callback(music_cog, mock_interaction)

        mock_container.queue_service.shuffle.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Shuffled" in args[0][0]

    @pytest.mark.asyncio
    async def test_shuffle_not_enough_tracks(self, music_cog, mock_interaction, mock_container):
        """Should handle not enough tracks."""
        mock_container.queue_service.shuffle = AsyncMock(return_value=False)

        await music_cog.shuffle.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Not enough" in args[0][0]


# =============================================================================
# /loop Command Tests
# =============================================================================


class TestLoopCommand:
    """Tests for /loop command."""

    @pytest.mark.asyncio
    async def test_loop_toggle_off(self, music_cog, mock_interaction, mock_container):
        """Should toggle loop to off."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value="off")

        await music_cog.loop.callback(music_cog, mock_interaction)

        mock_container.queue_service.toggle_loop.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "➡️" in args[0][0]
        assert "off" in args[0][0]

    @pytest.mark.asyncio
    async def test_loop_toggle_track(self, music_cog, mock_interaction, mock_container):
        """Should toggle loop to track."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value="track")

        await music_cog.loop.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "🔂" in args[0][0]
        assert "track" in args[0][0]

    @pytest.mark.asyncio
    async def test_loop_toggle_queue(self, music_cog, mock_interaction, mock_container):
        """Should toggle loop to queue."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value="queue")

        await music_cog.loop.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "🔁" in args[0][0]
        assert "queue" in args[0][0]


# =============================================================================
# /remove Command Tests
# =============================================================================


class TestRemoveCommand:
    """Tests for /remove command."""

    @pytest.mark.asyncio
    async def test_remove_success(self, music_cog, mock_interaction, mock_container, sample_track):
        """Should remove track at position."""
        mock_container.queue_service.remove = AsyncMock(return_value=sample_track)

        await music_cog.remove.callback(music_cog, mock_interaction, position=2)

        # Should convert from 1-based to 0-based
        mock_container.queue_service.remove.assert_called_once_with(111111111, 1)
        args = mock_interaction.response.send_message.call_args
        assert "Removed" in args[0][0]

    @pytest.mark.asyncio
    async def test_remove_invalid_position(self, music_cog, mock_interaction, mock_container):
        """Should handle invalid position."""
        mock_container.queue_service.remove = AsyncMock(return_value=None)

        await music_cog.remove.callback(music_cog, mock_interaction, position=100)

        args = mock_interaction.response.send_message.call_args
        assert "No track" in args[0][0]

    @pytest.mark.asyncio
    async def test_remove_position_must_be_positive(self, music_cog, mock_interaction):
        """Should reject non-positive positions."""
        await music_cog.remove.callback(music_cog, mock_interaction, position=0)

        args = mock_interaction.response.send_message.call_args
        assert "1 or greater" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_remove_negative_position(self, music_cog, mock_interaction):
        """Should reject negative positions."""
        await music_cog.remove.callback(music_cog, mock_interaction, position=-1)

        args = mock_interaction.response.send_message.call_args
        assert "1 or greater" in args[0][0].lower()


# =============================================================================
# /clear Command Tests
# =============================================================================


class TestClearCommand:
    """Tests for /clear command."""

    @pytest.mark.asyncio
    async def test_clear_success(self, music_cog, mock_interaction, mock_container):
        """Should clear queue."""
        mock_container.queue_service.clear = AsyncMock(return_value=5)

        await music_cog.clear.callback(music_cog, mock_interaction)

        mock_container.queue_service.clear.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "5 tracks" in args[0][0]

    @pytest.mark.asyncio
    async def test_clear_already_empty(self, music_cog, mock_interaction, mock_container):
        """Should handle already empty queue."""
        mock_container.queue_service.clear = AsyncMock(return_value=0)

        await music_cog.clear.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "empty" in args[0][0].lower()


# =============================================================================
# /leave Command Tests
# =============================================================================


class TestLeaveCommand:
    """Tests for /leave command."""

    @pytest.mark.asyncio
    async def test_leave_success(self, music_cog, mock_interaction, mock_container):
        """Should disconnect from voice."""
        mock_container.voice_adapter.disconnect = AsyncMock(return_value=True)

        await music_cog.leave.callback(music_cog, mock_interaction)

        mock_container.playback_service.cleanup_guild.assert_called_once_with(111111111)
        mock_container.voice_adapter.disconnect.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Disconnected" in args[0][0]

    @pytest.mark.asyncio
    async def test_leave_not_connected(self, music_cog, mock_interaction, mock_container):
        """Should handle not connected."""
        mock_container.voice_adapter.disconnect = AsyncMock(return_value=False)

        await music_cog.leave.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Not connected" in args[0][0]


# =============================================================================
# /played Command Tests
# =============================================================================


class TestPlayedCommand:
    """Tests for /played command."""

    @pytest.mark.asyncio
    async def test_played_with_history(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display play history."""
        mock_container.history_repository.get_recent = AsyncMock(return_value=[sample_track])

        await music_cog.played.callback(music_cog, mock_interaction)

        mock_container.history_repository.get_recent.assert_called_once_with(111111111, limit=10)
        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_played_no_history(self, music_cog, mock_interaction, mock_container):
        """Should handle no play history."""
        mock_container.history_repository.get_recent = AsyncMock(return_value=[])

        await music_cog.played.callback(music_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "No tracks" in args[0][0]


# =============================================================================
# Message State Management Tests
# =============================================================================


class TestMessageStateManagement:
    """Tests for message state tracking and updates."""

    @pytest.mark.asyncio
    async def test_track_now_playing_message(self, music_cog, sample_track):
        """Should track now playing message."""
        music_cog._track_now_playing_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        state = music_cog._message_state_by_guild[111]
        assert state.now_playing is not None
        assert state.now_playing.message_id == 333

    @pytest.mark.asyncio
    async def test_track_queued_message(self, music_cog, sample_track):
        """Should track queued message."""
        music_cog._track_queued_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        state = music_cog._message_state_by_guild[111]
        assert len(state.queued) == 1

    @pytest.mark.asyncio
    async def test_on_track_finished_clears_now_playing(
        self, music_cog, mock_bot, mock_container, sample_track
    ):
        """Should clear now playing message on track finish."""
        # Setup tracked message
        music_cog._track_now_playing_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        # Mock fetch_message to return a message
        mock_message = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        # No session (no next track)
        mock_container.session_repository.get.return_value = None

        await music_cog._on_track_finished(111, sample_track)

        # Should have edited message
        mock_message.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_track_finished_promotes_queued_message(
        self, music_cog, mock_bot, mock_container, sample_track
    ):
        """Should promote queued message to now playing."""
        # Track queued message
        music_cog._track_queued_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=444
        )

        # Mock session with current track
        session = GuildPlaybackSession(guild_id=111)
        session.current_track = sample_track
        mock_container.session_repository.get.return_value = session

        # Mock message fetching
        mock_message = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        # Create a finished track (different from current)
        finished_track = Track(
            id=TrackId("finished"),
            title="Finished",
            webpage_url="https://example.com/finished",
            requested_by_id=111,
        )

        await music_cog._on_track_finished(111, finished_track)

        # Should promote queued to now playing
        state = music_cog._message_state_by_guild[111]
        assert state.now_playing is not None
        assert state.now_playing.message_id == 444


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_command_without_guild(self, music_cog, mock_interaction):
        """Should reject commands without guild."""
        mock_interaction.guild = None

        await music_cog.play.callback(music_cog, mock_interaction, "test")

        # Should have sent error about server-only
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_not_in_voice(self, music_cog, mock_interaction):
        """Should reject when user not in voice."""
        mock_interaction.user.voice = None

        await music_cog.pause.callback(music_cog, mock_interaction)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_warmup_not_passed(self, music_cog, mock_interaction, mock_container):
        """Should reject when warmup not passed."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 10

        await music_cog.pause.callback(music_cog, mock_interaction)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_fetch_failure_graceful(self, music_cog, mock_bot, sample_track):
        """Should handle message fetch failures gracefully."""
        music_cog._track_now_playing_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        # Make fetch fail
        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Not found")
        )

        # Should not raise
        await music_cog._on_track_finished(111, sample_track)

    @pytest.mark.asyncio
    async def test_message_edit_failure_graceful(self, music_cog, mock_bot, sample_track):
        """Should handle message edit failures gracefully."""
        music_cog._track_now_playing_message(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        mock_message = AsyncMock()
        mock_message.edit.side_effect = discord.HTTPException(MagicMock(), "Cannot edit")
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        # Should not raise
        await music_cog._on_track_finished(111, sample_track)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complex workflows."""

    @pytest.mark.asyncio
    async def test_full_playback_workflow(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle full play -> pause -> resume -> stop workflow."""
        # Play
        mock_container.voice_adapter.is_connected.return_value = True
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)
        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.should_start = True
        enqueue_result.track = sample_track
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await music_cog.play.callback(music_cog, mock_interaction, "test")

        # Pause
        mock_container.playback_service.pause_playback = AsyncMock(return_value=True)
        await music_cog.pause.callback(music_cog, mock_interaction)

        # Resume
        mock_container.playback_service.resume_playback = AsyncMock(return_value=True)
        await music_cog.resume.callback(music_cog, mock_interaction)

        # Stop
        mock_container.playback_service.stop_playback = AsyncMock(return_value=True)
        mock_container.queue_service.clear = AsyncMock(return_value=1)
        await music_cog.stop.callback(music_cog, mock_interaction)

        # All should have succeeded
        assert mock_container.playback_service.start_playback.called
        assert mock_container.playback_service.pause_playback.called
        assert mock_container.playback_service.resume_playback.called
        assert mock_container.playback_service.stop_playback.called

    @pytest.mark.asyncio
    async def test_queue_management_workflow(
        self, music_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle queue -> shuffle -> remove -> clear workflow."""
        # View queue
        queue_info = MagicMock()
        queue_info.total_tracks = 5
        queue_info.current_track = sample_track
        queue_info.tracks = [sample_track] * 5
        queue_info.total_duration = 900
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await music_cog.queue.callback(music_cog, mock_interaction, page=1)

        # Shuffle
        mock_container.queue_service.shuffle = AsyncMock(return_value=True)
        await music_cog.shuffle.callback(music_cog, mock_interaction)

        # Remove
        mock_container.queue_service.remove = AsyncMock(return_value=sample_track)
        await music_cog.remove.callback(music_cog, mock_interaction, position=3)

        # Clear
        mock_container.queue_service.clear = AsyncMock(return_value=4)
        await music_cog.clear.callback(music_cog, mock_interaction)

        # All should have succeeded
        assert mock_container.queue_service.get_queue.called
        assert mock_container.queue_service.shuffle.called
        assert mock_container.queue_service.remove.called
        assert mock_container.queue_service.clear.called
