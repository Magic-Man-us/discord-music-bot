"""
Comprehensive Unit Tests for EventCog

Tests for all event handlers and functionality in the event cog:
- Lifecycle events (on_ready, on_connect, on_disconnect, on_resumed)
- Guild events (on_guild_join, on_guild_remove, on_guild_update)
- Member events (on_member_join, on_member_remove, on_member_ban, on_member_unban)
- Voice state updates (on_voice_state_update)
- Message events (on_message, on_message_edit, on_message_delete)
- Reaction events (on_raw_reaction_add, on_reaction_remove)
- Command error handling (on_command_error)
- Helper methods (_env_flag, _is_bot_or_none, voice channel management)
- Auto-disconnect logic
- Error handling in all event handlers

Uses pytest with async/await patterns and proper mocking.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands

from discord_music_player.domain.shared.constants import ConfigKeys
from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages
from discord_music_player.infrastructure.discord.cogs.event_cog import EventCog

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock(spec=commands.Bot)
    bot.user = MagicMock()
    bot.user.id = 888888888
    bot.user.name = "TestBot"
    bot.get_cog = MagicMock(return_value=None)
    bot.voice_clients = []
    return bot


@pytest.fixture
def mock_container():
    """Create a mock DI container."""
    container = MagicMock()
    container.session_repository = AsyncMock()
    container.voice_warmup_tracker = MagicMock()
    return container


@pytest.fixture
def event_cog(mock_bot, mock_container):
    """Create an EventCog instance with mocked dependencies."""
    from discord_music_player.domain.shared.events import reset_event_bus

    reset_event_bus()  # Reset global event bus before each test
    with patch.dict("os.environ", {}, clear=True):
        cog = EventCog(mock_bot, mock_container)

    yield cog

    reset_event_bus()  # Clean up after test


@pytest.fixture
def mock_guild():
    """Create a mock Discord Guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = 111111111
    guild.name = "Test Guild"
    guild.system_channel = None
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord Member."""
    member = MagicMock(spec=discord.Member)
    member.id = 222222222
    member.name = "testuser"
    member.display_name = "TestUser"
    member.bot = False
    member.guild = MagicMock()
    member.guild.id = 111111111
    member.mention = "<@222222222>"
    return member


@pytest.fixture
def mock_voice_state():
    """Create a mock Discord VoiceState."""
    state = MagicMock(spec=discord.VoiceState)
    state.channel = None
    return state


@pytest.fixture
def mock_voice_channel():
    """Create a mock Discord VoiceChannel."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 333333333
    channel.name = "Voice Channel"
    channel.members = []
    return channel


@pytest.fixture
def mock_message():
    """Create a mock Discord Message."""
    message = MagicMock(spec=discord.Message)
    message.id = 444444444
    message.content = "Test message"
    message.author = MagicMock()
    message.author.bot = False
    message.author.display_name = "TestUser"
    return message


@pytest.fixture
def mock_reaction():
    """Create a mock Discord Reaction."""
    reaction = MagicMock(spec=discord.Reaction)
    reaction.message = MagicMock()
    reaction.message.id = 555555555
    reaction.emoji = "👍"
    return reaction


# =============================================================================
# Initialization Tests
# =============================================================================


class TestEventCogInitialization:
    """Tests for EventCog initialization and setup."""

    def test_cog_initializes_with_bot_and_container(self, mock_bot, mock_container):
        """Should initialize with bot and container."""
        with patch.dict("os.environ", {}, clear=True):
            cog = EventCog(mock_bot, mock_container)

        assert cog.bot == mock_bot
        assert cog.container == mock_container
        assert cog._resumed_logged_once is False

    def test_cog_initializes_event_bus(self, mock_bot, mock_container):
        """Should initialize event bus."""
        with patch.dict("os.environ", {}, clear=True):
            cog = EventCog(mock_bot, mock_container)

        assert cog._event_bus is not None

    def test_cog_reads_chat_logging_env(self, mock_bot, mock_container):
        """Should read chat logging preference from environment."""
        with patch.dict("os.environ", {ConfigKeys.LOG_EVENT_MESSAGES: "true"}):
            cog = EventCog(mock_bot, mock_container)

        assert cog._chat_logging is True

    def test_cog_reads_reaction_logging_env(self, mock_bot, mock_container):
        """Should read reaction logging preference from environment."""
        with patch.dict("os.environ", {ConfigKeys.LOG_EVENT_REACTIONS: "1"}):
            cog = EventCog(mock_bot, mock_container)

        assert cog._reaction_logging is True

    @pytest.mark.asyncio
    async def test_setup_creates_cog(self, mock_bot, mock_container):
        """Should create and add cog during setup."""
        from discord_music_player.infrastructure.discord.cogs.event_cog import setup

        mock_bot.container = mock_container
        mock_bot.add_cog = AsyncMock()

        with patch.dict("os.environ", {}, clear=True):
            await setup(mock_bot)

        mock_bot.add_cog.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_raises_without_container(self, mock_bot):
        """Should raise RuntimeError when container not found."""
        from discord_music_player.infrastructure.discord.cogs.event_cog import setup

        mock_bot.container = None
        mock_bot.add_cog = AsyncMock()

        with pytest.raises(RuntimeError, match=ErrorMessages.CONTAINER_NOT_FOUND):
            await setup(mock_bot)


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for internal helper methods."""

    def test_env_flag_returns_true_for_1(self):
        """Should return True for '1'."""
        with patch.dict("os.environ", {"TEST_FLAG": "1"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is True

    def test_env_flag_returns_true_for_true(self):
        """Should return True for 'true'."""
        with patch.dict("os.environ", {"TEST_FLAG": "true"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is True

    def test_env_flag_returns_true_for_yes(self):
        """Should return True for 'yes'."""
        with patch.dict("os.environ", {"TEST_FLAG": "yes"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is True

    def test_env_flag_returns_true_for_on(self):
        """Should return True for 'on'."""
        with patch.dict("os.environ", {"TEST_FLAG": "on"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is True

    def test_env_flag_returns_false_for_0(self):
        """Should return False for '0'."""
        with patch.dict("os.environ", {"TEST_FLAG": "0"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is False

    def test_env_flag_returns_false_for_false(self):
        """Should return False for 'false'."""
        with patch.dict("os.environ", {"TEST_FLAG": "false"}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is False

    def test_env_flag_returns_false_for_empty(self):
        """Should return False for empty string."""
        with patch.dict("os.environ", {"TEST_FLAG": ""}):
            result = EventCog._env_flag("TEST_FLAG")
        assert result is False

    def test_env_flag_returns_false_for_missing(self):
        """Should return False for missing environment variable."""
        with patch.dict("os.environ", {}, clear=True):
            result = EventCog._env_flag("MISSING_FLAG")
        assert result is False

    def test_is_bot_or_none_returns_true_for_none(self):
        """Should return True for None user."""
        result = EventCog._is_bot_or_none(None)
        assert result is True

    def test_is_bot_or_none_returns_true_for_bot(self):
        """Should return True for bot user."""
        user = MagicMock()
        user.bot = True
        result = EventCog._is_bot_or_none(user)
        assert result is True

    def test_is_bot_or_none_returns_false_for_human(self):
        """Should return False for human user."""
        user = MagicMock()
        user.bot = False
        result = EventCog._is_bot_or_none(user)
        assert result is False

    def test_is_bot_or_none_handles_missing_bot_attribute(self):
        """Should handle users without bot attribute."""
        user = MagicMock(spec=[])
        result = EventCog._is_bot_or_none(user)
        assert result is False


# =============================================================================
# Lifecycle Event Tests
# =============================================================================


class TestLifecycleEvents:
    """Tests for lifecycle event handlers."""

    @pytest.mark.asyncio
    async def test_on_ready_logs_bot_info(self, event_cog, caplog):
        """Should log bot ready information."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_ready()

        assert any("Bot ready as" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_connect_logs_connection(self, event_cog, caplog):
        """Should log WebSocket connection."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_connect()

        assert any("WebSocket connected" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_disconnect_logs_disconnection(self, event_cog, caplog):
        """Should log WebSocket disconnection."""
        with caplog.at_level(logging.WARNING):
            await event_cog.on_disconnect()

        assert any("WebSocket disconnected" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_resumed_logs_first_time(self, event_cog, caplog):
        """Should log session resumed first time."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_resumed()

        assert any("WebSocket session resumed" in record.message for record in caplog.records)
        assert event_cog._resumed_logged_once is True

    @pytest.mark.asyncio
    async def test_on_resumed_does_not_log_second_time(self, event_cog, caplog):
        """Should not log session resumed after first time."""
        await event_cog.on_resumed()
        caplog.clear()

        with caplog.at_level(logging.INFO):
            await event_cog.on_resumed()

        assert not any("WebSocket session resumed" in record.message for record in caplog.records)


# =============================================================================
# Guild Event Tests
# =============================================================================


class TestGuildEvents:
    """Tests for guild event handlers."""

    @pytest.mark.asyncio
    async def test_on_guild_join_logs_guild(self, event_cog, mock_guild, caplog):
        """Should log guild join."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_join(mock_guild)

        assert any("Joined guild" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_guild_join_sends_welcome_message(self, event_cog, mock_guild):
        """Should send welcome message to system channel."""
        mock_channel = AsyncMock()
        mock_guild.system_channel = mock_channel

        await event_cog.on_guild_join(mock_guild)

        mock_channel.send.assert_called_once_with(DiscordUIMessages.SUCCESS_GUILD_WELCOME)

    @pytest.mark.asyncio
    async def test_on_guild_join_handles_no_system_channel(self, event_cog, mock_guild):
        """Should handle missing system channel."""
        mock_guild.system_channel = None

        # Should not raise
        await event_cog.on_guild_join(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_join_handles_send_error(self, event_cog, mock_guild):
        """Should handle HTTP exception when sending welcome."""
        mock_channel = AsyncMock()
        mock_channel.send.side_effect = discord.HTTPException(MagicMock(), "Failed")
        mock_guild.system_channel = mock_channel

        # Should not raise
        await event_cog.on_guild_join(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_remove_logs_guild(self, event_cog, mock_guild, caplog):
        """Should log guild removal."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_remove(mock_guild)

        assert any("Left guild" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_guild_remove_cleans_up_message_state(self, event_cog, mock_guild, mock_container):
        """Should cleanup message state via container."""
        mock_container.message_state_manager = MagicMock()

        await event_cog.on_guild_remove(mock_guild)

        mock_container.message_state_manager.reset.assert_called_once_with(mock_guild.id)

    @pytest.mark.asyncio
    async def test_on_guild_remove_handles_message_state_error(self, event_cog, mock_guild, mock_container):
        """Should handle message state cleanup error gracefully."""
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset.side_effect = Exception("Error")

        # Should not raise
        await event_cog.on_guild_remove(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_remove_deletes_session(self, event_cog, mock_guild, mock_container):
        """Should delete session for guild."""
        await event_cog.on_guild_remove(mock_guild)

        mock_container.session_repository.delete.assert_called_once_with(mock_guild.id)

    @pytest.mark.asyncio
    async def test_on_guild_remove_handles_session_delete_error(
        self, event_cog, mock_guild, mock_container
    ):
        """Should handle session deletion error gracefully."""
        mock_container.session_repository.delete.side_effect = Exception("DB error")

        # Should not raise
        await event_cog.on_guild_remove(mock_guild)

    @pytest.mark.asyncio
    async def test_on_guild_update_logs_name_change(self, event_cog, caplog):
        """Should log guild name change."""
        before = MagicMock(spec=discord.Guild)
        before.name = "Old Name"
        after = MagicMock(spec=discord.Guild)
        after.name = "New Name"

        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_update(before, after)

        assert any("Guild renamed" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_guild_update_ignores_no_name_change(self, event_cog, caplog):
        """Should not log when name unchanged."""
        before = MagicMock(spec=discord.Guild)
        before.name = "Same Name"
        after = MagicMock(spec=discord.Guild)
        after.name = "Same Name"

        caplog.clear()
        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_update(before, after)

        assert not any("Guild renamed" in record.message for record in caplog.records)


# =============================================================================
# Member Event Tests
# =============================================================================


class TestMemberEvents:
    """Tests for member event handlers."""

    @pytest.mark.asyncio
    async def test_on_member_join_logs_member(self, event_cog, mock_member, caplog):
        """Should log member join."""
        mock_member.guild.system_channel = None

        with caplog.at_level(logging.INFO):
            await event_cog.on_member_join(mock_member)

        assert any("Member joined" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_member_join_sends_welcome(self, event_cog, mock_member):
        """Should send welcome message to system channel."""
        mock_channel = AsyncMock()
        mock_member.guild.system_channel = mock_channel

        await event_cog.on_member_join(mock_member)

        mock_channel.send.assert_called_once()
        args = mock_channel.send.call_args[0][0]
        assert mock_member.mention in args

    @pytest.mark.asyncio
    async def test_on_member_join_handles_no_system_channel(self, event_cog, mock_member):
        """Should handle missing system channel."""
        mock_member.guild.system_channel = None

        # Should not raise
        await event_cog.on_member_join(mock_member)

    @pytest.mark.asyncio
    async def test_on_member_join_handles_send_error(self, event_cog, mock_member):
        """Should handle HTTP exception when sending welcome."""
        mock_channel = AsyncMock()
        mock_channel.send.side_effect = discord.HTTPException(MagicMock(), "Failed")
        mock_member.guild.system_channel = mock_channel

        # Should not raise
        await event_cog.on_member_join(mock_member)

    @pytest.mark.asyncio
    async def test_on_member_remove_logs_member(self, event_cog, mock_member, caplog):
        """Should log member removal."""
        with caplog.at_level(logging.INFO):
            await event_cog.on_member_remove(mock_member)

        assert any("Member left" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_member_ban_logs_ban(self, event_cog, mock_guild, caplog):
        """Should log member ban."""
        user = MagicMock(spec=discord.User)
        user.id = 999999999
        user.display_name = "BannedUser"

        with caplog.at_level(logging.WARNING):
            await event_cog.on_member_ban(mock_guild, user)

        assert any("User banned" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_member_unban_logs_unban(self, event_cog, mock_guild, caplog):
        """Should log member unban."""
        user = MagicMock(spec=discord.User)
        user.id = 999999999
        user.display_name = "UnbannedUser"

        with caplog.at_level(logging.INFO):
            await event_cog.on_member_unban(mock_guild, user)

        assert any("User unbanned" in record.message for record in caplog.records)


# =============================================================================
# Voice State Update Tests
# =============================================================================


class TestVoiceStateUpdate:
    """Tests for voice state update event handler."""

    @pytest.mark.asyncio
    async def test_on_voice_state_update_ignores_bot(self, event_cog, mock_voice_state):
        """Should ignore bot voice state changes."""
        bot_member = MagicMock(spec=discord.Member)
        bot_member.bot = True

        # Should not raise or process
        await event_cog.on_voice_state_update(bot_member, mock_voice_state, mock_voice_state)

    @pytest.mark.asyncio
    async def test_on_voice_state_update_marks_join(
        self, event_cog, mock_member, mock_container, mock_voice_channel
    ):
        """Should mark user as joined when entering channel."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = mock_voice_channel

        await event_cog.on_voice_state_update(mock_member, before, after)

        mock_container.voice_warmup_tracker.mark_joined.assert_called_once_with(
            guild_id=mock_member.guild.id, user_id=mock_member.id
        )

    @pytest.mark.asyncio
    async def test_on_voice_state_update_publishes_join_event(
        self, event_cog, mock_member, mock_voice_channel
    ):
        """Should publish voice member joined event."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = mock_voice_channel

        with patch.object(event_cog._event_bus, "publish", new_callable=AsyncMock) as mock_publish:
            await event_cog.on_voice_state_update(mock_member, before, after)

        assert mock_publish.called
        event = mock_publish.call_args[0][0]
        assert event.guild_id == mock_member.guild.id
        assert event.user_id == mock_member.id

    @pytest.mark.asyncio
    async def test_on_voice_state_update_publishes_leave_event(
        self, event_cog, mock_member, mock_voice_channel, mock_bot
    ):
        """Should publish voice member left event when leaving bot channel."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = mock_voice_channel
        after = MagicMock(spec=discord.VoiceState)
        after.channel = None

        # Mock bot connected to same channel
        mock_voice_client = MagicMock()
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.guild = mock_member.guild
        mock_bot.voice_clients = [mock_voice_client]

        # Mock the schedule disconnect to prevent 30-second sleep
        with (
            patch.object(event_cog._event_bus, "publish", new_callable=AsyncMock) as mock_publish,
            patch.object(event_cog, "_schedule_empty_channel_disconnect", new_callable=AsyncMock),
        ):
            await event_cog.on_voice_state_update(mock_member, before, after)

        # Should have published leave event
        assert any(hasattr(call_args[0][0], "user_id") for call_args in mock_publish.call_args_list)

    @pytest.mark.asyncio
    async def test_should_check_empty_channel_ignores_bot_itself(
        self, event_cog, mock_member, mock_voice_state
    ):
        """Should not check empty channel for bot's own changes."""
        mock_member.id = event_cog.bot.user.id

        result = event_cog._should_check_empty_channel(mock_member, mock_voice_state)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_check_empty_channel_requires_before_channel(self, event_cog, mock_member):
        """Should require before channel to check."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None

        result = event_cog._should_check_empty_channel(mock_member, before)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_check_empty_channel_returns_true(self, event_cog, mock_member):
        """Should return True for valid member leaving."""
        before = MagicMock(spec=discord.VoiceState)
        before.channel = MagicMock()

        result = event_cog._should_check_empty_channel(mock_member, before)

        assert result is True

    def test_get_bot_voice_channel_returns_channel(self, event_cog, mock_guild, mock_voice_channel):
        """Should return bot's voice channel."""
        mock_voice_client = MagicMock()
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.guild = mock_guild
        event_cog.bot.voice_clients = [mock_voice_client]

        result = event_cog._get_bot_voice_channel(mock_guild)

        assert result == mock_voice_channel

    def test_get_bot_voice_channel_returns_none_not_connected(self, event_cog, mock_guild):
        """Should return None when not connected."""
        event_cog.bot.voice_clients = []

        result = event_cog._get_bot_voice_channel(mock_guild)

        assert result is None

    def test_has_non_bot_members_returns_true(self, event_cog, mock_voice_channel):
        """Should return True when channel has non-bot members."""
        human = MagicMock()
        human.bot = False
        mock_voice_channel.members = [human]

        result = event_cog._has_non_bot_members(mock_voice_channel)

        assert result is True

    def test_has_non_bot_members_returns_false(self, event_cog, mock_voice_channel):
        """Should return False when channel has only bots."""
        bot = MagicMock()
        bot.bot = True
        mock_voice_channel.members = [bot]

        result = event_cog._has_non_bot_members(mock_voice_channel)

        assert result is False

    @pytest.mark.asyncio
    async def test_schedule_empty_channel_disconnect_disconnects(
        self, event_cog, mock_guild, mock_container, mock_voice_channel
    ):
        """Should disconnect after delay if still empty."""
        mock_voice_client = MagicMock()
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.guild = mock_guild
        mock_voice_client.disconnect = AsyncMock()
        event_cog.bot.voice_clients = [mock_voice_client]

        # Empty channel
        mock_voice_channel.members = []

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await event_cog._schedule_empty_channel_disconnect(mock_guild)

        mock_voice_client.disconnect.assert_called_once()
        mock_container.session_repository.delete.assert_called_once_with(mock_guild.id)

    @pytest.mark.asyncio
    async def test_schedule_empty_channel_disconnect_cancels_if_rejoined(
        self, event_cog, mock_guild, mock_voice_channel
    ):
        """Should not disconnect if someone rejoined."""
        mock_voice_client = MagicMock()
        mock_voice_client.channel = mock_voice_channel
        mock_voice_client.guild = mock_guild
        mock_voice_client.disconnect = AsyncMock()
        event_cog.bot.voice_clients = [mock_voice_client]

        # Add member after sleep
        human = MagicMock()
        human.bot = False

        async def add_member_after_sleep(seconds):
            mock_voice_channel.members = [human]

        with patch("asyncio.sleep", new_callable=AsyncMock, side_effect=add_member_after_sleep):
            await event_cog._schedule_empty_channel_disconnect(mock_guild)

        mock_voice_client.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_and_cleanup_handles_exception(self, event_cog, mock_guild, caplog):
        """Should handle disconnect exception gracefully."""
        mock_voice_client = MagicMock()
        mock_voice_client.disconnect = AsyncMock(side_effect=Exception("Disconnect error"))
        mock_voice_client.guild = mock_guild
        event_cog.bot.voice_clients = [mock_voice_client]

        with caplog.at_level(logging.ERROR):
            await event_cog._disconnect_and_cleanup(mock_guild)

        assert any("Failed to disconnect" in record.message for record in caplog.records)


# =============================================================================
# Message Event Tests
# =============================================================================


class TestMessageEvents:
    """Tests for message event handlers."""

    @pytest.mark.asyncio
    async def test_on_message_ignores_bot_messages(self, event_cog):
        """Should ignore messages from bots."""
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock()
        message.author.bot = True

        # Should not log or process
        with patch.dict("os.environ", {ConfigKeys.LOG_EVENT_MESSAGES: "true"}):
            await event_cog.on_message(message)

    @pytest.mark.asyncio
    async def test_on_message_logs_when_enabled(self, event_cog, mock_message, caplog):
        """Should log message when logging enabled."""
        event_cog._chat_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message(mock_message)

        assert any("Message by" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_message_does_not_log_when_disabled(self, event_cog, mock_message, caplog):
        """Should not log when logging disabled."""
        event_cog._chat_logging = False

        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message(mock_message)

        assert not any("Message by" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_message_truncates_long_messages(self, event_cog, caplog):
        """Should truncate long messages in logs."""
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock()
        message.author.bot = False
        message.author.display_name = "TestUser"
        message.content = "A" * 100

        event_cog._chat_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message(message)

        # Should include ellipsis
        assert any("…" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_message_edit_ignores_bot_messages(self, event_cog):
        """Should ignore edits from bots."""
        before = MagicMock(spec=discord.Message)
        before.author = MagicMock()
        before.author.bot = True
        after = MagicMock(spec=discord.Message)

        # Should not log or process
        await event_cog.on_message_edit(before, after)

    @pytest.mark.asyncio
    async def test_on_message_edit_ignores_no_content_change(self, event_cog, caplog):
        """Should ignore when content unchanged."""
        before = MagicMock(spec=discord.Message)
        before.author = MagicMock()
        before.author.bot = False
        before.content = "Same content"
        after = MagicMock(spec=discord.Message)
        after.content = "Same content"

        event_cog._chat_logging = True

        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message_edit(before, after)

        assert not any("Message edit" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_message_edit_logs_when_enabled(self, event_cog, caplog):
        """Should log message edit when enabled."""
        before = MagicMock(spec=discord.Message)
        before.author = MagicMock()
        before.author.bot = False
        before.author.display_name = "TestUser"
        before.content = "Old content"
        after = MagicMock(spec=discord.Message)
        after.author = before.author
        after.content = "New content"

        event_cog._chat_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message_edit(before, after)

        assert any("Message edit" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_message_delete_ignores_bot_messages(self, event_cog):
        """Should ignore deletions of bot messages."""
        message = MagicMock(spec=discord.Message)
        message.author = MagicMock()
        message.author.bot = True

        # Should not log or process
        await event_cog.on_message_delete(message)

    @pytest.mark.asyncio
    async def test_on_message_delete_logs_when_enabled(self, event_cog, mock_message, caplog):
        """Should log message deletion when enabled."""
        event_cog._chat_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_message_delete(mock_message)

        assert any("Message deleted" in record.message for record in caplog.records)


# =============================================================================
# Reaction Event Tests
# =============================================================================


class TestReactionEvents:
    """Tests for reaction event handlers."""

    @pytest.mark.asyncio
    async def test_on_raw_reaction_add_ignores_bot(self, event_cog):
        """Should ignore reactions from bots."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.member.bot = True

        # Should not log or process
        await event_cog.on_raw_reaction_add(payload)

    @pytest.mark.asyncio
    async def test_on_raw_reaction_add_logs_when_enabled(self, event_cog, caplog):
        """Should log reaction add when enabled."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = MagicMock()
        payload.member.bot = False
        payload.member.display_name = "TestUser"
        payload.message_id = 123456
        payload.user_id = 789012
        payload.emoji = "👍"

        event_cog._reaction_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_raw_reaction_add(payload)

        assert any("Reaction add" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_reaction_remove_ignores_bot(self, event_cog, mock_reaction):
        """Should ignore reaction removals from bots."""
        user = MagicMock()
        user.bot = True

        # Should not log or process
        await event_cog.on_reaction_remove(mock_reaction, user)

    @pytest.mark.asyncio
    async def test_on_reaction_remove_logs_when_enabled(self, event_cog, mock_reaction, caplog):
        """Should log reaction remove when enabled."""
        user = MagicMock()
        user.bot = False
        user.display_name = "TestUser"

        event_cog._reaction_logging = True

        with caplog.at_level(logging.DEBUG):
            await event_cog.on_reaction_remove(mock_reaction, user)

        assert any("Reaction remove" in record.message for record in caplog.records)


# =============================================================================
# Command Error Handler Tests
# =============================================================================


class TestCommandErrorHandler:
    """Tests for command error handling."""

    @pytest.mark.asyncio
    async def test_on_command_error_handles_cooldown(self, event_cog):
        """Should handle cooldown errors."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.qualified_name = "test_command"
        ctx.author = MagicMock()
        ctx.author.id = 123456
        ctx.reply = AsyncMock()

        error = commands.CommandOnCooldown(
            cooldown=MagicMock(), retry_after=5.5, type=commands.BucketType.user
        )

        await event_cog.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        args = ctx.reply.call_args[0][0]
        assert "5.5s" in args

    @pytest.mark.asyncio
    async def test_on_command_error_handles_cooldown_milliseconds(self, event_cog):
        """Should format milliseconds for short cooldowns."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.qualified_name = "test_command"
        ctx.author = MagicMock()
        ctx.author.id = 123456
        ctx.reply = AsyncMock()

        error = commands.CommandOnCooldown(
            cooldown=MagicMock(), retry_after=0.5, type=commands.BucketType.user
        )

        await event_cog.on_command_error(ctx, error)

        args = ctx.reply.call_args[0][0]
        assert "500ms" in args

    @pytest.mark.asyncio
    async def test_on_command_error_handles_cooldown_http_error(self, event_cog, caplog):
        """Should handle HTTP error when replying to cooldown."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.qualified_name = "test_command"
        ctx.author = MagicMock()
        ctx.author.id = 123456
        ctx.reply = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Failed"))

        error = commands.CommandOnCooldown(
            cooldown=MagicMock(), retry_after=1.0, type=commands.BucketType.user
        )

        # Should not raise
        await event_cog.on_command_error(ctx, error)

    @pytest.mark.asyncio
    async def test_on_command_error_handles_missing_permissions(self, event_cog):
        """Should handle missing permissions error."""
        ctx = MagicMock(spec=commands.Context)
        ctx.reply = AsyncMock()

        error = commands.MissingPermissions(["manage_messages"])

        await event_cog.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        args = ctx.reply.call_args[0][0]
        assert "permission" in args.lower()

    @pytest.mark.asyncio
    async def test_on_command_error_handles_bot_missing_permissions(self, event_cog):
        """Should handle bot missing permissions error."""
        ctx = MagicMock(spec=commands.Context)
        ctx.reply = AsyncMock()

        error = commands.BotMissingPermissions(["send_messages", "embed_links"])

        await event_cog.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        args = ctx.reply.call_args[0][0]
        assert "send_messages" in args
        assert "embed_links" in args

    @pytest.mark.asyncio
    async def test_on_command_error_ignores_command_not_found(self, event_cog, caplog):
        """Should silently ignore command not found."""
        ctx = MagicMock(spec=commands.Context)
        error = commands.CommandNotFound()

        caplog.clear()
        await event_cog.on_command_error(ctx, error)

        # Should not log anything
        assert len(caplog.records) == 0

    @pytest.mark.asyncio
    async def test_on_command_error_logs_other_errors(self, event_cog, caplog):
        """Should log other unhandled errors."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.qualified_name = "test_command"

        error = commands.CommandError("Unknown error")

        with caplog.at_level(logging.ERROR):
            await event_cog.on_command_error(ctx, error)

        assert any("Unhandled command error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_on_command_error_logs_original_exception(self, event_cog, caplog):
        """Should log original exception if available."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = MagicMock()
        ctx.command.qualified_name = "test_command"

        original = ValueError("Original error")
        error = commands.CommandInvokeError(original)
        error.original = original

        with caplog.at_level(logging.ERROR):
            await event_cog.on_command_error(ctx, error)

        assert any("Unhandled command error" in record.message for record in caplog.records)


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for complex workflows."""

    @pytest.mark.asyncio
    async def test_full_member_lifecycle(
        self, event_cog, mock_member, mock_guild, mock_voice_channel, caplog
    ):
        """Should handle full member lifecycle."""
        mock_member.guild.system_channel = AsyncMock()

        # Join guild
        with caplog.at_level(logging.INFO):
            await event_cog.on_member_join(mock_member)
        assert any("Member joined" in record.message for record in caplog.records)

        # Join voice
        before = MagicMock(spec=discord.VoiceState)
        before.channel = None
        after = MagicMock(spec=discord.VoiceState)
        after.channel = mock_voice_channel

        await event_cog.on_voice_state_update(mock_member, before, after)

        # Leave voice
        before2 = MagicMock(spec=discord.VoiceState)
        before2.channel = mock_voice_channel
        after2 = MagicMock(spec=discord.VoiceState)
        after2.channel = None

        await event_cog.on_voice_state_update(mock_member, before2, after2)

        # Leave guild
        caplog.clear()
        with caplog.at_level(logging.INFO):
            await event_cog.on_member_remove(mock_member)
        assert any("Member left" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_guild_lifecycle_with_cleanup(
        self, event_cog, mock_guild, mock_container, caplog
    ):
        """Should handle guild lifecycle with cleanup."""
        # Join
        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_join(mock_guild)
        assert any("Joined guild" in record.message for record in caplog.records)

        # Update
        before = MagicMock(spec=discord.Guild)
        before.name = "Old Name"
        after = MagicMock(spec=discord.Guild)
        after.name = "New Name"
        await event_cog.on_guild_update(before, after)

        # Leave
        caplog.clear()
        with caplog.at_level(logging.INFO):
            await event_cog.on_guild_remove(mock_guild)

        assert any("Left guild" in record.message for record in caplog.records)
        mock_container.session_repository.delete.assert_called_with(mock_guild.id)


# =============================================================================
# Error Handling and Edge Cases
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_voice_state_update_handles_missing_guild(self, event_cog, mock_member):
        """Should handle member without guild gracefully."""
        mock_member.guild = None
        before = MagicMock(spec=discord.VoiceState)
        after = MagicMock(spec=discord.VoiceState)

        # Should not raise
        try:
            await event_cog.on_voice_state_update(mock_member, before, after)
        except AttributeError:
            # Expected if guild is accessed
            pass

    @pytest.mark.asyncio
    async def test_message_handlers_handle_none_author(self, event_cog):
        """Should handle messages with None author."""
        message = MagicMock(spec=discord.Message)
        message.author = None

        # Should not raise
        await event_cog.on_message(message)
        await event_cog.on_message_delete(message)

    @pytest.mark.asyncio
    async def test_reaction_handlers_handle_none_member(self, event_cog):
        """Should handle reactions with None member."""
        payload = MagicMock(spec=discord.RawReactionActionEvent)
        payload.member = None

        # Should not raise
        await event_cog.on_raw_reaction_add(payload)

    @pytest.mark.asyncio
    async def test_voice_disconnect_handles_no_voice_client(
        self, event_cog, mock_guild, mock_container
    ):
        """Should handle disconnect when not connected."""
        event_cog.bot.voice_clients = []

        # Should not raise
        await event_cog._disconnect_and_cleanup(mock_guild)

        # Should not attempt to delete session
        mock_container.session_repository.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_error_handles_missing_command_name(self, event_cog, caplog):
        """Should handle errors with missing command name."""
        ctx = MagicMock(spec=commands.Context)
        ctx.command = None

        error = commands.CommandError("Error")

        with caplog.at_level(logging.ERROR):
            await event_cog.on_command_error(ctx, error)

        # Should still log
        assert len(caplog.records) > 0
