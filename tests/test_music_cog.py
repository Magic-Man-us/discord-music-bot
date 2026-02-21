"""
Comprehensive Unit Tests for Cogs (PlaybackCog, QueueCog, SkipCog, NowPlayingCog)
and extracted infrastructure (MessageStateManager, voice_guards).

Tests for all slash commands and functionality:
- /play, /skip, /stop, /pause, /resume, /queue, /current, /clear
- /loop, /shuffle, /remove, /leave, /played
- Permission checks and validation
- Discord interaction mocking
- Error handling
- Integration with container services
- Edge cases (empty queue, invalid positions, etc.)

Uses pytest with async/await patterns and proper mocking.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import LoopMode, PlaybackState, TrackId
from discord_music_player.domain.voting.value_objects import VoteResult
from discord_music_player.infrastructure.discord.cogs.playback_cog import PlaybackCog
from discord_music_player.infrastructure.discord.cogs.queue_cog import QueueCog
from discord_music_player.infrastructure.discord.cogs.skip_cog import SkipCog
from discord_music_player.infrastructure.discord.cogs.now_playing_cog import NowPlayingCog
from discord_music_player.infrastructure.discord.services.message_state_manager import (
    GuildMessageState,
    MessageStateManager,
    TrackedMessage,
    TrackKey,
)
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    can_force_skip,
    ensure_user_in_voice_and_warm,
    ensure_voice,
    ensure_voice_warmup,
    get_member,
    send_ephemeral,
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

    # Mock message_state_manager
    container.message_state_manager = MagicMock(spec=MessageStateManager)
    container.message_state_manager.build_now_playing_embed = MagicMock(
        return_value=discord.Embed(title="🎵 Now Playing")
    )
    container.message_state_manager.format_queued_line = MagicMock(
        return_value="⏭️ Queued for play: Test"
    )
    container.message_state_manager.format_finished_line = MagicMock(
        return_value="✅ Finished playing: Test"
    )
    container.message_state_manager.get_state = MagicMock(return_value=GuildMessageState())
    container.message_state_manager.track_now_playing = MagicMock()
    container.message_state_manager.track_queued = MagicMock()
    container.message_state_manager.reset = MagicMock()
    container.message_state_manager.clear_all = MagicMock()
    container.message_state_manager.on_track_finished = AsyncMock()
    container.message_state_manager.promote_next_track = AsyncMock()

    # Mock radio service
    container.radio_service = MagicMock()
    container.radio_service.disable_radio = MagicMock()

    # Mock auto_skip_on_requester_leave
    container.auto_skip_on_requester_leave = MagicMock()
    container.auto_skip_on_requester_leave.set_on_requester_left_callback = MagicMock()

    return container


@pytest.fixture
def playback_cog(mock_bot, mock_container):
    """Create a PlaybackCog instance with mocked dependencies."""
    return PlaybackCog(mock_bot, mock_container)


@pytest.fixture
def queue_cog(mock_bot, mock_container):
    """Create a QueueCog instance with mocked dependencies."""
    return QueueCog(mock_bot, mock_container)


@pytest.fixture
def skip_cog(mock_bot, mock_container):
    """Create a SkipCog instance with mocked dependencies."""
    return SkipCog(mock_bot, mock_container)


@pytest.fixture
def now_playing_cog(mock_bot, mock_container):
    """Create a NowPlayingCog instance with mocked dependencies."""
    return NowPlayingCog(mock_bot, mock_container)


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
# Helper Classes Tests (MessageStateManager data classes)
# =============================================================================


class TestTrackKey:
    """Tests for TrackKey helper class."""

    def test_from_track_creates_key(self, sample_track):
        """Should create track key from track."""
        key = TrackKey.from_track(sample_track)

        assert key.track_id == "test123"
        assert key.requested_by_id == 333333333
        assert key.requested_at == sample_track.requested_at

    def test_track_keys_equal_for_same_track(self, sample_track):
        """Should create equal keys for same track."""
        key1 = TrackKey.from_track(sample_track)
        key2 = TrackKey.from_track(sample_track)

        assert key1 == key2

    def test_track_keys_frozen(self, sample_track):
        """Should be immutable (frozen)."""
        key = TrackKey.from_track(sample_track)

        with pytest.raises(AttributeError):
            key.track_id = "modified"


class TestTrackedMessage:
    """Tests for TrackedMessage helper class."""

    def test_from_track_creates_message(self, sample_track):
        """Should create tracked message from track."""
        msg = TrackedMessage.from_track(sample_track, channel_id=123, message_id=456)

        assert msg.channel_id == 123
        assert msg.message_id == 456
        assert msg.track_key.track_id == "test123"


class TestGuildMessageState:
    """Tests for GuildMessageState helper class."""

    def test_initial_state_empty(self):
        """Should start with no messages."""
        state = GuildMessageState()

        assert state.now_playing is None
        assert len(state.queued) == 0

    def test_pop_matching_queued_finds_and_removes(self, sample_track):
        """Should find and remove matching queued message."""
        state = GuildMessageState()
        msg = TrackedMessage.from_track(sample_track, channel_id=1, message_id=2)
        state.queued.append(msg)

        found = state.pop_matching_queued(sample_track)

        assert found == msg
        assert len(state.queued) == 0

    def test_pop_matching_queued_returns_none_if_not_found(self, sample_track):
        """Should return None if track not found."""
        state = GuildMessageState()

        found = state.pop_matching_queued(sample_track)

        assert found is None

    def test_pop_matching_queued_removes_only_matching(self, sample_track):
        """Should only remove the matching track."""
        state = GuildMessageState()

        other_track = Track(
            id=TrackId("other"),
            title="Other",
            webpage_url="https://youtube.com/watch?v=other",
            requested_by_id=999,
        )

        msg1 = TrackedMessage.from_track(sample_track, channel_id=1, message_id=1)
        msg2 = TrackedMessage.from_track(other_track, channel_id=1, message_id=2)

        state.queued.append(msg1)
        state.queued.append(msg2)

        found = state.pop_matching_queued(sample_track)

        assert found == msg1
        assert len(state.queued) == 1
        assert state.queued[0] == msg2


# =============================================================================
# PlaybackCog Initialization Tests
# =============================================================================


class TestPlaybackCogInitialization:
    """Tests for PlaybackCog initialization and lifecycle."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        cog = PlaybackCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container

    @pytest.mark.asyncio
    async def test_cog_load_registers_callback(self, playback_cog, mock_container):
        """Should register track finished callback on load."""
        await playback_cog.cog_load()

        mock_container.playback_service.set_track_finished_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_cog_unload_clears_message_state(self, playback_cog, mock_container):
        """Should clear message state on unload."""
        await playback_cog.cog_unload()

        mock_container.message_state_manager.clear_all.assert_called_once()


# =============================================================================
# Voice Guard Function Tests
# =============================================================================


class TestVoiceGuards:
    """Tests for extracted voice guard functions."""

    @pytest.mark.asyncio
    async def test_send_ephemeral_not_responded(self, mock_interaction):
        """Should use response.send_message when not responded."""
        await send_ephemeral(mock_interaction, "Test message")

        mock_interaction.response.send_message.assert_called_once_with(
            "Test message", ephemeral=True
        )

    @pytest.mark.asyncio
    async def test_send_ephemeral_already_responded(self, mock_interaction):
        """Should use followup.send when already responded."""
        mock_interaction.response.is_done.return_value = True

        await send_ephemeral(mock_interaction, "Test message")

        mock_interaction.followup.send.assert_called_once_with("Test message", ephemeral=True)

    @pytest.mark.asyncio
    async def test_get_member_success(self, mock_interaction):
        """Should return member when valid."""
        member = await get_member(mock_interaction)

        assert member == mock_interaction.user

    @pytest.mark.asyncio
    async def test_get_member_no_guild(self, mock_interaction):
        """Should return None when no guild."""
        mock_interaction.guild = None

        member = await get_member(mock_interaction)

        assert member is None
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_member_not_member(self, mock_interaction):
        """Should return None when user is not a Member."""
        mock_interaction.user = MagicMock(spec=discord.User)  # Not a Member

        member = await get_member(mock_interaction)

        assert member is None

    @pytest.mark.asyncio
    async def test_ensure_voice_warmup_passed(self, mock_interaction, mock_container):
        """Should return True when warmup passed."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 0

        result = await ensure_voice_warmup(
            mock_interaction, mock_interaction.user, mock_container.voice_warmup_tracker
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_voice_warmup_required(self, mock_interaction, mock_container):
        """Should return False and notify when warmup required."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 5

        result = await ensure_voice_warmup(
            mock_interaction, mock_interaction.user, mock_container.voice_warmup_tracker
        )

        assert result is False
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_user_in_voice_and_warm_success(self, mock_interaction, mock_container):
        """Should return True when user in voice and warm."""
        result = await ensure_user_in_voice_and_warm(
            mock_interaction, mock_container.voice_warmup_tracker
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_ensure_user_in_voice_and_warm_not_in_voice(
        self, mock_interaction, mock_container
    ):
        """Should return False when user not in voice."""
        mock_interaction.user.voice = None

        result = await ensure_user_in_voice_and_warm(
            mock_interaction, mock_container.voice_warmup_tracker
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_ensure_voice_connects_bot(self, mock_interaction, mock_container):
        """Should connect bot to voice channel."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=True)

        result = await ensure_voice(
            mock_interaction,
            mock_container.voice_warmup_tracker,
            mock_container.voice_adapter,
        )

        assert result is True
        mock_container.voice_adapter.ensure_connected.assert_called_once_with(111111111, 444444444)

    @pytest.mark.asyncio
    async def test_ensure_voice_fails_to_connect(self, mock_interaction, mock_container):
        """Should return False when cannot connect to voice."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=False)

        result = await ensure_voice(
            mock_interaction,
            mock_container.voice_warmup_tracker,
            mock_container.voice_adapter,
        )

        assert result is False

    def test_can_force_skip_admin(self):
        """Should allow admin to force skip."""
        user = MagicMock(spec=discord.Member)
        user.guild_permissions.administrator = True
        user.id = 123

        assert can_force_skip(user, {999}) is True

    def test_can_force_skip_owner(self):
        """Should allow owner to force skip."""
        user = MagicMock(spec=discord.Member)
        user.guild_permissions.administrator = False
        user.id = 999

        assert can_force_skip(user, {999}) is True

    def test_can_force_skip_denied(self):
        """Should deny regular user."""
        user = MagicMock(spec=discord.Member)
        user.guild_permissions.administrator = False
        user.id = 123

        assert can_force_skip(user, {999}) is False


# =============================================================================
# MessageStateManager Formatting Tests
# =============================================================================


class TestMessageStateManagerFormatting:
    """Tests for MessageStateManager formatting methods."""

    def test_format_requester_with_id(self, sample_track):
        """Should format requester with user mention."""
        result = MessageStateManager.format_requester(sample_track)
        assert result == "<@333333333>"

    def test_format_requester_with_name_only(self):
        """Should format requester with name when no ID."""
        track = Track(
            id=TrackId("test"),
            title="Test",
            webpage_url="https://example.com",
            requested_by_name="TestUser",
        )
        result = MessageStateManager.format_requester(track)
        assert result == "TestUser"

    def test_format_requester_unknown(self):
        """Should return Unknown when no requester info."""
        track = Track(
            id=TrackId("test"),
            title="Test",
            webpage_url="https://example.com",
        )
        result = MessageStateManager.format_requester(track)
        assert result == "Unknown"

    def test_format_queued_line(self, sample_track):
        """Should format queued message line."""
        result = MessageStateManager.format_queued_line(sample_track)
        assert "⏭️" in result
        assert "Queued for play" in result
        assert sample_track.title in result
        assert "<@333333333>" in result

    def test_format_finished_line(self, sample_track):
        """Should format finished message line."""
        result = MessageStateManager.format_finished_line(sample_track)
        assert "✅" in result
        assert "Finished playing" in result
        assert sample_track.title in result

    def test_build_now_playing_embed(self, sample_track):
        """Should build now playing embed."""
        embed = MessageStateManager.build_now_playing_embed(sample_track)
        assert isinstance(embed, discord.Embed)
        assert embed.title == "🎵 Now Playing"
        assert sample_track.title in embed.description
        assert embed.thumbnail.url == sample_track.thumbnail_url
        assert len(embed.fields) == 3  # Duration, Artist, Likes

    def test_build_now_playing_embed_minimal_track(self):
        """Should build embed for track with minimal info."""
        track = Track(
            id=TrackId("test"),
            title="Minimal Track",
            webpage_url="https://example.com",
        )
        embed = MessageStateManager.build_now_playing_embed(track)
        assert isinstance(embed, discord.Embed)
        assert track.title in embed.description


# =============================================================================
# /play Command Tests
# =============================================================================


class TestPlayCommand:
    """Tests for /play command."""

    @pytest.mark.asyncio
    async def test_play_successful_enqueue(
        self, playback_cog, mock_interaction, mock_container, sample_track
    ):
        """Should successfully enqueue and play track."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)

        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.position = 0
        enqueue_result.should_start = True
        enqueue_result.track = sample_track
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await playback_cog.play.callback(playback_cog, mock_interaction, "test query")

        mock_interaction.response.defer.assert_called_once()
        mock_container.audio_resolver.resolve.assert_called_once_with("test query")
        mock_container.queue_service.enqueue.assert_called_once()
        mock_container.playback_service.start_playback.assert_called_once_with(
            111111111, start_seconds=None
        )

    @pytest.mark.asyncio
    async def test_play_track_not_found(self, playback_cog, mock_interaction, mock_container):
        """Should handle track not found."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=None)

        await playback_cog.play.callback(playback_cog, mock_interaction, "nonexistent track")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "Couldn't find" in args[0][0]

    @pytest.mark.asyncio
    async def test_play_voice_connection_failed(
        self, playback_cog, mock_interaction, mock_container
    ):
        """Should handle voice connection failure."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=False)
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=False)
        mock_container.audio_resolver.resolve = AsyncMock()

        await playback_cog.play.callback(playback_cog, mock_interaction, "test query")

        mock_container.audio_resolver.resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_play_enqueue_failed(
        self, playback_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle enqueue failure."""
        mock_container.voice_adapter.is_connected = MagicMock(return_value=True)
        mock_container.audio_resolver.resolve = AsyncMock(return_value=sample_track)

        enqueue_result = MagicMock()
        enqueue_result.success = False
        enqueue_result.message = "Queue is full"
        mock_container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)

        await playback_cog.play.callback(playback_cog, mock_interaction, "test query")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "Queue is full" in args[0][0]

    @pytest.mark.asyncio
    async def test_play_queued_not_started(
        self, playback_cog, mock_interaction, mock_container, sample_track
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

        await playback_cog.play.callback(playback_cog, mock_interaction, "test query")

        mock_container.playback_service.start_playback.assert_not_called()
        mock_interaction.followup.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_exception_handling(self, playback_cog, mock_interaction, mock_container):
        """Should handle exceptions gracefully."""
        mock_container.voice_adapter.is_connected.return_value = True
        mock_container.audio_resolver.resolve.side_effect = Exception("Network error")

        await playback_cog.play.callback(playback_cog, mock_interaction, "test query")

        mock_interaction.followup.send.assert_called_once()
        args = mock_interaction.followup.send.call_args
        assert "error" in args[0][0].lower()


# =============================================================================
# /skip Command Tests
# =============================================================================


class TestSkipCommand:
    """Tests for /skip command."""

    @pytest.mark.asyncio
    async def test_skip_vote_skip_success(self, skip_cog, mock_interaction, mock_container):
        """Should handle vote skip successfully."""
        result = MagicMock()
        result.result = VoteResult.VOTE_RECORDED
        result.votes_current = 2
        result.votes_needed = 3
        result.action_executed = False
        mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)

        await skip_cog.skip.callback(skip_cog, mock_interaction, force=False)

        mock_container.vote_skip_handler.handle.assert_called_once()
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_threshold_met(
        self, skip_cog, mock_interaction, mock_container, sample_track
    ):
        """Should skip when threshold met."""
        result = MagicMock()
        result.result = VoteResult.THRESHOLD_MET
        result.votes_current = 3
        result.votes_needed = 3
        result.action_executed = True
        mock_container.vote_skip_handler.handle = AsyncMock(return_value=result)
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await skip_cog.skip.callback(skip_cog, mock_interaction, force=False)

        mock_container.playback_service.skip_track.assert_called_once_with(111111111)

    @pytest.mark.asyncio
    async def test_skip_force_by_admin(
        self, skip_cog, mock_interaction, mock_container, sample_track
    ):
        """Should allow force skip by admin."""
        mock_interaction.user.guild_permissions.administrator = True
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await skip_cog.skip.callback(skip_cog, mock_interaction, force=True)

        mock_container.playback_service.skip_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_force_by_owner(
        self, skip_cog, mock_interaction, mock_container, sample_track
    ):
        """Should allow force skip by owner."""
        mock_interaction.user.id = 999999999  # Owner ID
        mock_container.playback_service.skip_track = AsyncMock(return_value=sample_track)

        await skip_cog.skip.callback(skip_cog, mock_interaction, force=True)

        mock_container.playback_service.skip_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_force_denied_for_regular_user(self, skip_cog, mock_interaction):
        """Should deny force skip for regular user."""
        await skip_cog.skip.callback(skip_cog, mock_interaction, force=True)

        mock_interaction.response.send_message.assert_called_once()
        args = mock_interaction.response.send_message.call_args
        assert "administrator" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_skip_nothing_playing(self, skip_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.skip_track = AsyncMock(return_value=None)
        mock_interaction.user.guild_permissions.administrator = True

        await skip_cog.skip.callback(skip_cog, mock_interaction, force=True)

        mock_interaction.response.send_message.assert_called_once()
        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /stop Command Tests
# =============================================================================


class TestStopCommand:
    """Tests for /stop command."""

    @pytest.mark.asyncio
    async def test_stop_success(self, playback_cog, mock_interaction, mock_container):
        """Should stop playback and clear queue."""
        mock_container.playback_service.stop_playback = AsyncMock(return_value=True)
        mock_container.queue_service.clear = AsyncMock(return_value=5)

        await playback_cog.stop.callback(playback_cog, mock_interaction)

        mock_container.playback_service.stop_playback.assert_called_once_with(111111111)
        mock_container.queue_service.clear.assert_called_once_with(111111111)
        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_nothing_playing(self, playback_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.stop_playback = AsyncMock(return_value=False)
        mock_container.queue_service.clear = AsyncMock(return_value=0)

        await playback_cog.stop.callback(playback_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /pause Command Tests
# =============================================================================


class TestPauseCommand:
    """Tests for /pause command."""

    @pytest.mark.asyncio
    async def test_pause_success(self, playback_cog, mock_interaction, mock_container):
        """Should pause playback."""
        mock_container.playback_service.pause_playback = AsyncMock(return_value=True)

        await playback_cog.pause.callback(playback_cog, mock_interaction)

        mock_container.playback_service.pause_playback.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Paused" in args[0][0]

    @pytest.mark.asyncio
    async def test_pause_nothing_playing(self, playback_cog, mock_interaction, mock_container):
        """Should handle nothing playing."""
        mock_container.playback_service.pause_playback = AsyncMock(return_value=False)

        await playback_cog.pause.callback(playback_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /resume Command Tests
# =============================================================================


class TestResumeCommand:
    """Tests for /resume command."""

    @pytest.mark.asyncio
    async def test_resume_success(self, playback_cog, mock_interaction, mock_container):
        """Should resume playback."""
        mock_container.playback_service.resume_playback = AsyncMock(return_value=True)

        await playback_cog.resume.callback(playback_cog, mock_interaction)

        mock_container.playback_service.resume_playback.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Resumed" in args[0][0]

    @pytest.mark.asyncio
    async def test_resume_nothing_paused(self, playback_cog, mock_interaction, mock_container):
        """Should handle nothing paused."""
        mock_container.playback_service.resume_playback = AsyncMock(return_value=False)

        await playback_cog.resume.callback(playback_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /queue Command Tests
# =============================================================================


class TestQueueCommand:
    """Tests for /queue command."""

    @pytest.mark.asyncio
    async def test_queue_empty(self, queue_cog, mock_interaction, mock_container):
        """Should handle empty queue."""
        queue_info = MagicMock()
        queue_info.total_tracks = 0
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await queue_cog.queue.callback(queue_cog, mock_interaction, page=1)

        args = mock_interaction.response.send_message.call_args
        assert "empty" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_queue_with_tracks(
        self, queue_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display queue with tracks."""
        queue_info = MagicMock()
        queue_info.total_tracks = 3
        queue_info.current_track = sample_track
        queue_info.tracks = [sample_track, sample_track, sample_track]
        queue_info.total_duration = 540
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await queue_cog.queue.callback(queue_cog, mock_interaction, page=1)

        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs
        embed = call_args.kwargs["embed"]
        assert "Queue" in embed.title

    @pytest.mark.asyncio
    async def test_queue_pagination(
        self, queue_cog, mock_interaction, mock_container, sample_track
    ):
        """Should handle pagination."""
        queue_info = MagicMock()
        queue_info.total_tracks = 25
        queue_info.current_track = None
        queue_info.tracks = [sample_track] * 25
        queue_info.total_duration = 4500
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await queue_cog.queue.callback(queue_cog, mock_interaction, page=2)

        mock_interaction.response.send_message.assert_called_once()


# =============================================================================
# /current Command Tests
# =============================================================================


class TestCurrentCommand:
    """Tests for /current command."""

    @pytest.mark.asyncio
    async def test_current_with_track(
        self, now_playing_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display current track."""
        queue_info = MagicMock()
        queue_info.current_track = sample_track
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await now_playing_cog.current.callback(now_playing_cog, mock_interaction)

        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_current_nothing_playing(self, now_playing_cog, mock_interaction, mock_container):
        """Should handle no current track."""
        queue_info = MagicMock()
        queue_info.current_track = None
        mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

        await now_playing_cog.current.callback(now_playing_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Nothing" in args[0][0]


# =============================================================================
# /shuffle Command Tests
# =============================================================================


class TestShuffleCommand:
    """Tests for /shuffle command."""

    @pytest.mark.asyncio
    async def test_shuffle_success(self, queue_cog, mock_interaction, mock_container):
        """Should shuffle queue."""
        mock_container.queue_service.shuffle = AsyncMock(return_value=True)

        await queue_cog.shuffle.callback(queue_cog, mock_interaction)

        mock_container.queue_service.shuffle.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Shuffled" in args[0][0]

    @pytest.mark.asyncio
    async def test_shuffle_not_enough_tracks(self, queue_cog, mock_interaction, mock_container):
        """Should handle not enough tracks."""
        mock_container.queue_service.shuffle = AsyncMock(return_value=False)

        await queue_cog.shuffle.callback(queue_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Not enough" in args[0][0]


# =============================================================================
# /loop Command Tests
# =============================================================================


class TestLoopCommand:
    """Tests for /loop command."""

    @pytest.mark.asyncio
    async def test_loop_toggle_off(self, queue_cog, mock_interaction, mock_container):
        """Should toggle loop to off."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value=LoopMode.OFF)

        await queue_cog.loop.callback(queue_cog, mock_interaction)

        mock_container.queue_service.toggle_loop.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "➡️" in args[0][0]
        assert "off" in args[0][0]

    @pytest.mark.asyncio
    async def test_loop_toggle_track(self, queue_cog, mock_interaction, mock_container):
        """Should toggle loop to track."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value=LoopMode.TRACK)

        await queue_cog.loop.callback(queue_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "🔂" in args[0][0]
        assert "track" in args[0][0]

    @pytest.mark.asyncio
    async def test_loop_toggle_queue(self, queue_cog, mock_interaction, mock_container):
        """Should toggle loop to queue."""
        mock_container.queue_service.toggle_loop = AsyncMock(return_value=LoopMode.QUEUE)

        await queue_cog.loop.callback(queue_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "🔁" in args[0][0]
        assert "queue" in args[0][0]


# =============================================================================
# /remove Command Tests
# =============================================================================


class TestRemoveCommand:
    """Tests for /remove command."""

    @pytest.mark.asyncio
    async def test_remove_success(self, queue_cog, mock_interaction, mock_container, sample_track):
        """Should remove track at position."""
        mock_container.queue_service.remove = AsyncMock(return_value=sample_track)

        await queue_cog.remove.callback(queue_cog, mock_interaction, position=2)

        # Should convert from 1-based to 0-based
        mock_container.queue_service.remove.assert_called_once_with(111111111, 1)
        args = mock_interaction.response.send_message.call_args
        assert "Removed" in args[0][0]

    @pytest.mark.asyncio
    async def test_remove_invalid_position(self, queue_cog, mock_interaction, mock_container):
        """Should handle invalid position."""
        mock_container.queue_service.remove = AsyncMock(return_value=None)

        await queue_cog.remove.callback(queue_cog, mock_interaction, position=100)

        args = mock_interaction.response.send_message.call_args
        assert "No track" in args[0][0]

    @pytest.mark.asyncio
    async def test_remove_position_must_be_positive(self, queue_cog, mock_interaction):
        """Should reject non-positive positions."""
        await queue_cog.remove.callback(queue_cog, mock_interaction, position=0)

        args = mock_interaction.response.send_message.call_args
        assert "1 or greater" in args[0][0].lower()

    @pytest.mark.asyncio
    async def test_remove_negative_position(self, queue_cog, mock_interaction):
        """Should reject negative positions."""
        await queue_cog.remove.callback(queue_cog, mock_interaction, position=-1)

        args = mock_interaction.response.send_message.call_args
        assert "1 or greater" in args[0][0].lower()


# =============================================================================
# /clear Command Tests
# =============================================================================


class TestClearCommand:
    """Tests for /clear command."""

    @pytest.mark.asyncio
    async def test_clear_success(self, queue_cog, mock_interaction, mock_container):
        """Should clear queue."""
        mock_container.queue_service.clear = AsyncMock(return_value=5)

        await queue_cog.clear.callback(queue_cog, mock_interaction)

        mock_container.queue_service.clear.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "5 tracks" in args[0][0]

    @pytest.mark.asyncio
    async def test_clear_already_empty(self, queue_cog, mock_interaction, mock_container):
        """Should handle already empty queue."""
        mock_container.queue_service.clear = AsyncMock(return_value=0)

        await queue_cog.clear.callback(queue_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "empty" in args[0][0].lower()


# =============================================================================
# /leave Command Tests
# =============================================================================


class TestLeaveCommand:
    """Tests for /leave command."""

    @pytest.mark.asyncio
    async def test_leave_success(self, playback_cog, mock_interaction, mock_container):
        """Should disconnect from voice."""
        mock_container.voice_adapter.disconnect = AsyncMock(return_value=True)

        await playback_cog.leave.callback(playback_cog, mock_interaction)

        mock_container.playback_service.cleanup_guild.assert_called_once_with(111111111)
        mock_container.voice_adapter.disconnect.assert_called_once_with(111111111)
        args = mock_interaction.response.send_message.call_args
        assert "Disconnected" in args[0][0]

    @pytest.mark.asyncio
    async def test_leave_not_connected(self, playback_cog, mock_interaction, mock_container):
        """Should handle not connected."""
        mock_container.voice_adapter.disconnect = AsyncMock(return_value=False)

        await playback_cog.leave.callback(playback_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "Not connected" in args[0][0]


# =============================================================================
# /played Command Tests
# =============================================================================


class TestPlayedCommand:
    """Tests for /played command."""

    @pytest.mark.asyncio
    async def test_played_with_history(
        self, now_playing_cog, mock_interaction, mock_container, sample_track
    ):
        """Should display play history."""
        mock_container.history_repository.get_recent = AsyncMock(return_value=[sample_track])

        await now_playing_cog.played.callback(now_playing_cog, mock_interaction)

        mock_container.history_repository.get_recent.assert_called_once_with(111111111, limit=10)
        call_args = mock_interaction.response.send_message.call_args
        assert "embed" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_played_no_history(self, now_playing_cog, mock_interaction, mock_container):
        """Should handle no play history."""
        mock_container.history_repository.get_recent = AsyncMock(return_value=[])

        await now_playing_cog.played.callback(now_playing_cog, mock_interaction)

        args = mock_interaction.response.send_message.call_args
        assert "No tracks" in args[0][0]


# =============================================================================
# Message State Management Tests
# =============================================================================


class TestMessageStateManagement:
    """Tests for MessageStateManager message tracking."""

    @pytest.fixture
    def msm(self, mock_bot):
        """Create a real MessageStateManager for testing."""
        return MessageStateManager(mock_bot)

    def test_track_now_playing_message(self, msm, sample_track):
        """Should track now playing message."""
        msm.track_now_playing(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        state = msm.get_state(111)
        assert state.now_playing is not None
        assert state.now_playing.message_id == 333

    def test_track_queued_message(self, msm, sample_track):
        """Should track queued message."""
        msm.track_queued(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        state = msm.get_state(111)
        assert len(state.queued) == 1

    @pytest.mark.asyncio
    async def test_on_track_finished_clears_now_playing(
        self, msm, mock_bot, sample_track
    ):
        """Should clear now playing message on track finish."""
        msm.track_now_playing(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        mock_message = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        await msm.on_track_finished(111, sample_track)

        mock_message.edit.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_track_finished_no_state_returns_early(self, msm, sample_track):
        """Should return early when no message state exists."""
        # No state for guild 999
        await msm.on_track_finished(999, sample_track)
        # Should not raise

    @pytest.mark.asyncio
    async def test_promote_next_track(
        self, msm, mock_bot, sample_track
    ):
        """Should promote queued message to now playing."""
        msm.track_queued(
            guild_id=111, track=sample_track, channel_id=222, message_id=444
        )

        mock_message = AsyncMock()
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        await msm.promote_next_track(111, sample_track)

        state = msm.get_state(111)
        assert state.now_playing is not None
        assert state.now_playing.message_id == 444

    def test_reset_clears_guild_state(self, msm, sample_track):
        """Should clear state for specific guild."""
        msm.track_now_playing(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )
        msm.track_now_playing(
            guild_id=222, track=sample_track, channel_id=222, message_id=444
        )

        msm.reset(111)

        # Guild 111 should be cleared
        state_111 = msm.get_state(111)
        assert state_111.now_playing is None

        # Guild 222 should remain
        state_222 = msm.get_state(222)
        assert state_222.now_playing is not None


# =============================================================================
# Edge Cases and Error Handling Tests
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_command_without_guild(self, playback_cog, mock_interaction):
        """Should reject commands without guild."""
        mock_interaction.guild = None

        await playback_cog.play.callback(playback_cog, mock_interaction, "test")

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_user_not_in_voice(self, playback_cog, mock_interaction):
        """Should reject when user not in voice."""
        mock_interaction.user.voice = None

        await playback_cog.pause.callback(playback_cog, mock_interaction)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_warmup_not_passed(self, playback_cog, mock_interaction, mock_container):
        """Should reject when warmup not passed."""
        mock_container.voice_warmup_tracker.remaining_seconds.return_value = 10

        await playback_cog.pause.callback(playback_cog, mock_interaction)

        mock_interaction.response.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_fetch_failure_graceful(self, mock_bot, sample_track):
        """Should handle message fetch failures gracefully."""
        msm = MessageStateManager(mock_bot)
        msm.track_now_playing(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Not found")
        )

        # Should not raise
        await msm.on_track_finished(111, sample_track)

    @pytest.mark.asyncio
    async def test_message_edit_failure_graceful(self, mock_bot, sample_track):
        """Should handle message edit failures gracefully."""
        msm = MessageStateManager(mock_bot)
        msm.track_now_playing(
            guild_id=111, track=sample_track, channel_id=222, message_id=333
        )

        mock_message = AsyncMock()
        mock_message.edit.side_effect = discord.HTTPException(MagicMock(), "Cannot edit")
        mock_channel = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        mock_bot.get_channel.return_value = mock_channel

        # Should not raise
        await msm.on_track_finished(111, sample_track)



# =============================================================================
# _on_requester_left Tests
# =============================================================================


class TestOnRequesterLeft:
    """Tests for _on_requester_left callback."""

    GUILD_ID = 111111111
    USER_ID = 333333333
    VIEW_PATH = "discord_music_player.infrastructure.discord.views.requester_left_view.RequesterLeftView"

    @pytest.mark.asyncio
    @patch(VIEW_PATH)
    async def test_sends_view_via_now_playing_channel(
        self, MockView, playback_cog, mock_bot, mock_container, sample_track
    ):
        """Should send view to the now-playing channel when message state exists."""
        # Setup now-playing message state
        state = GuildMessageState()
        state.now_playing = TrackedMessage.from_track(
            sample_track, channel_id=222, message_id=333
        )
        mock_container.message_state_manager.get_state.return_value = state

        # Mock channel returned by bot.get_channel
        mock_channel = MagicMock(spec=discord.abc.Messageable)
        mock_message = MagicMock()
        mock_channel.send = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        # Mock the view instance
        mock_view_instance = MagicMock()
        MockView.return_value = mock_view_instance

        await playback_cog._on_requester_left(self.GUILD_ID, self.USER_ID, sample_track)

        mock_channel.send.assert_called_once()
        call_kwargs = mock_channel.send.call_args
        assert call_kwargs[1]["view"] is mock_view_instance
        mock_view_instance.set_message.assert_called_once_with(mock_message)

    @pytest.mark.asyncio
    @patch(VIEW_PATH)
    async def test_falls_back_to_system_channel(
        self, MockView, playback_cog, mock_bot, mock_container, sample_track
    ):
        """Should fall back to guild system_channel when no message state."""
        # No now_playing in state
        mock_container.message_state_manager.get_state.return_value = GuildMessageState()

        mock_system_channel = MagicMock(spec=discord.abc.Messageable)
        mock_message = MagicMock()
        mock_system_channel.send = AsyncMock(return_value=mock_message)

        mock_guild = MagicMock()
        mock_guild.system_channel = mock_system_channel
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        MockView.return_value = MagicMock()

        await playback_cog._on_requester_left(self.GUILD_ID, self.USER_ID, sample_track)

        mock_system_channel.send.assert_called_once()

    @pytest.mark.asyncio
    @patch(VIEW_PATH)
    async def test_no_channel_auto_skips(
        self, MockView, playback_cog, mock_bot, mock_container, sample_track
    ):
        """Should auto-skip when no channel can be found (guild is None)."""
        mock_container.message_state_manager.get_state.return_value = GuildMessageState()
        mock_bot.get_guild = MagicMock(return_value=None)

        await playback_cog._on_requester_left(self.GUILD_ID, self.USER_ID, sample_track)

        mock_container.playback_service.skip_track.assert_called_once_with(self.GUILD_ID)
        MockView.assert_not_called()

    @pytest.mark.asyncio
    @patch(VIEW_PATH)
    async def test_guild_without_system_channel_auto_skips(
        self, MockView, playback_cog, mock_bot, mock_container, sample_track
    ):
        """Should auto-skip when guild exists but has no system_channel."""
        mock_container.message_state_manager.get_state.return_value = GuildMessageState()
        mock_guild = MagicMock()
        mock_guild.system_channel = None
        mock_bot.get_guild = MagicMock(return_value=mock_guild)

        await playback_cog._on_requester_left(self.GUILD_ID, self.USER_ID, sample_track)

        mock_container.playback_service.skip_track.assert_called_once_with(self.GUILD_ID)
        MockView.assert_not_called()

    @pytest.mark.asyncio
    @patch(VIEW_PATH)
    async def test_content_format(
        self, MockView, playback_cog, mock_bot, mock_container, sample_track
    ):
        """Should format content with user mention and truncated track title."""
        state = GuildMessageState()
        state.now_playing = TrackedMessage.from_track(
            sample_track, channel_id=222, message_id=333
        )
        mock_container.message_state_manager.get_state.return_value = state

        mock_channel = MagicMock(spec=discord.abc.Messageable)
        mock_channel.send = AsyncMock(return_value=MagicMock())
        mock_bot.get_channel.return_value = mock_channel
        MockView.return_value = MagicMock()

        await playback_cog._on_requester_left(self.GUILD_ID, self.USER_ID, sample_track)

        content = mock_channel.send.call_args[0][0]
        assert f"<@{self.USER_ID}>" in content
        assert sample_track.title in content
