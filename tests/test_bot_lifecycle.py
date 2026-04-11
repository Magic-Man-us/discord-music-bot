"""
Unit Tests for Bot Lifecycle

Comprehensive tests for src/infrastructure/discord/bot.py covering all bot lifecycle
aspects with 40 test cases across 9 test classes.

Test Coverage:

1. TestBotInitialization (6 tests):
   - Verifies correct Discord intents configuration
   - Command prefix setup from settings
   - Help command disabled
   - Container and settings storage
   - Shutdown event creation
   - Container.set_bot() called

2. TestSetupHook (10 tests):
   - Container initialization during setup
   - Stale session reset
   - Cog loading
   - Global slash command error handler setup
   - Cleanup job start
   - Command sync when enabled/disabled
   - Error handling for container init, cleanup start, and sync failures

3. TestResetStaleSessions (4 tests):
   - Handling empty session lists
   - Resetting sessions with current tracks to IDLE
   - Skipping already idle sessions
   - Error handling during reset

4. TestLoadCogs (2 tests):
   - Loading all 5 cogs (music, admin, health, info, event)
   - Continuing on individual cog load failures

5. TestSyncCommands (4 tests):
   - Global command sync
   - Test guild sync
   - Guild sync error handling
   - Global sync error handling

6. TestAppCommandErrorHandler (4 tests):
   - Sending ephemeral error responses
   - Using followup when already responded
   - Extracting original errors from wrappers
   - Handling send failures gracefully

7. TestOnReady (1 test):
   - Setting bot presence to "Listening to /play"

8. TestBotClose (7 tests):
   - Stopping cleanup job
   - Disconnecting all voice clients
   - Voice disconnect error handling
   - Container shutdown
   - Container shutdown error handling
   - Cleanup job stop error handling
   - Shutdown event set

9. TestCreateBot (2 tests):
   - Factory function returns MusicBot instance
   - Arguments passed correctly

All tests use proper async/await patterns, mock Discord dependencies,
and follow the project's testing conventions.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = MagicMock()
    settings.discord.command_prefix = "!"
    settings.discord.sync_on_startup = False
    settings.discord.test_guild_ids = []
    return settings


@pytest.fixture
def mock_container():
    """Create mock container with all required properties."""
    container = MagicMock()
    container.initialize = AsyncMock()
    container.shutdown = AsyncMock()
    container.set_bot = MagicMock()

    # Mock repositories
    container.session_repository = AsyncMock()
    container.session_repository.get_all_active = AsyncMock(return_value=[])
    container.session_repository.save = AsyncMock()

    # Mock cleanup job
    cleanup_job = MagicMock()
    cleanup_job.start = MagicMock()
    cleanup_job.stop = AsyncMock()
    type(container).cleanup_job = PropertyMock(return_value=cleanup_job)

    return container


# =============================================================================
# Bot Initialization Tests
# =============================================================================


class TestBotInitialization:
    """Tests for MusicBot initialization."""

    @pytest.mark.asyncio
    async def test_init_sets_intents(self, mock_container, mock_settings):
        """Should initialize bot with correct intents."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        assert bot.intents.message_content is True
        assert bot.intents.voice_states is True
        assert bot.intents.guilds is True
        assert bot.intents.members is True

    @pytest.mark.asyncio
    async def test_init_sets_command_prefix(self, mock_container, mock_settings):
        """Should set command prefix from settings."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.command_prefix = "?"
        bot = MusicBot(container=mock_container, settings=mock_settings)

        assert bot.command_prefix == "?"

    @pytest.mark.asyncio
    async def test_init_disables_default_help(self, mock_container, mock_settings):
        """Should disable default help command."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        assert bot.help_command is None

    @pytest.mark.asyncio
    async def test_init_stores_container_and_settings(self, mock_container, mock_settings):
        """Should store container and settings references."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        assert bot.container is mock_container
        assert bot.settings is mock_settings

    @pytest.mark.asyncio
    async def test_init_creates_shutdown_event(self, mock_container, mock_settings):
        """Should create shutdown event."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        assert isinstance(bot._shutdown_event, asyncio.Event)
        assert not bot._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_init_calls_set_bot_on_container(self, mock_container, mock_settings):
        """Should call set_bot on container."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        mock_container.set_bot.assert_called_once_with(bot)


# =============================================================================
# Setup Hook Tests
# =============================================================================


class TestSetupHook:
    """Tests for MusicBot.setup_hook method."""

    @pytest.mark.asyncio
    async def test_setup_hook_initializes_container(self, mock_container, mock_settings):
        """Should initialize container during setup."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                await bot.setup_hook()

        mock_container.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_ready_resumes_sessions(self, mock_container, mock_settings):
        """Should resume sessions during on_ready (after guild cache is populated)."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        bot._connection._guilds = {}  # simulate empty guild cache for user property
        bot._connection.user = MagicMock()

        with patch.object(bot, "_resume_sessions", new_callable=AsyncMock) as mock_resume:
            with patch.object(bot, "change_presence", new_callable=AsyncMock):
                await bot.on_ready()

        mock_resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_loads_cogs(self, mock_container, mock_settings):
        """Should load all cogs during setup."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock) as mock_load:
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                await bot.setup_hook()

        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_sets_error_handler(self, mock_container, mock_settings):
        """Should set global slash command error handler."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                await bot.setup_hook()

        assert bot.tree.on_error is not None

    @pytest.mark.asyncio
    async def test_setup_hook_starts_cleanup_job(self, mock_container, mock_settings):
        """Should start cleanup job during setup."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                await bot.setup_hook()

        mock_container.cleanup_job.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_syncs_when_enabled(self, mock_container, mock_settings):
        """Should sync commands when sync_on_startup is True."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.sync_on_startup = True
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                with patch.object(bot, "_sync_commands", new_callable=AsyncMock) as mock_sync:
                    await bot.setup_hook()

        mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_skips_sync_when_disabled(self, mock_container, mock_settings):
        """Should not sync commands when sync_on_startup is False."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.sync_on_startup = False
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                with patch.object(bot, "_sync_commands", new_callable=AsyncMock) as mock_sync:
                    await bot.setup_hook()

        mock_sync.assert_not_called()

    @pytest.mark.asyncio
    async def test_setup_hook_handles_container_init_error(self, mock_container, mock_settings):
        """Should raise error when container initialization fails."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.initialize.side_effect = Exception("Database error")
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with pytest.raises(Exception, match="Database error"):
            await bot.setup_hook()

    @pytest.mark.asyncio
    async def test_setup_hook_handles_cleanup_start_error(self, mock_container, mock_settings):
        """Should handle cleanup job start errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.cleanup_job.start.side_effect = Exception("Cleanup error")
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                # Should not raise
                await bot.setup_hook()

    @pytest.mark.asyncio
    async def test_setup_hook_handles_sync_error(self, mock_container, mock_settings):
        """Should handle command sync errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.sync_on_startup = True
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock):
                with patch.object(
                    bot,
                    "_sync_commands",
                    new_callable=AsyncMock,
                    side_effect=Exception("Sync error"),
                ):
                    # Should not raise
                    await bot.setup_hook()


# =============================================================================
# Stale Session Reset Tests
# =============================================================================


class TestResumeSessions:
    """Tests for MusicBot._resume_sessions method."""

    @pytest.mark.asyncio
    async def test_resume_sessions_no_sessions(self, mock_container, mock_settings):
        """Should handle no active sessions gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.session_repository.get_all_active.return_value = []
        bot = MusicBot(container=mock_container, settings=mock_settings)

        await bot._resume_sessions()

        mock_container.session_repository.get_all_active.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_sessions_resets_when_guild_not_found(self, mock_container, mock_settings):
        """Should reset sessions when guild is not found."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
        from discord_music_player.domain.music.enums import PlaybackState
        from discord_music_player.domain.music.wrappers import TrackId
        from discord_music_player.infrastructure.discord.bot import MusicBot

        # Create session with current track
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = Track(
            id=TrackId(value="test"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test",
        )
        session.state = PlaybackState.PLAYING

        mock_container.session_repository.get_all_active.return_value = [session]
        bot = MusicBot(container=mock_container, settings=mock_settings)
        # Bot has no guilds by default, so guild lookup will fail

        await bot._resume_sessions()

        # Session should be reset when guild not found
        assert session.state == PlaybackState.IDLE
        assert session.current_track is None
        mock_container.session_repository.save.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_resume_sessions_skips_idle_sessions(self, mock_container, mock_settings):
        """Should skip sessions that are already idle with no tracks."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession
        from discord_music_player.domain.music.enums import PlaybackState
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session = GuildPlaybackSession(guild_id=123456)
        session.state = PlaybackState.IDLE
        session.current_track = None

        mock_container.session_repository.get_all_active.return_value = [session]
        bot = MusicBot(container=mock_container, settings=mock_settings)

        await bot._resume_sessions()

        # Should skip idle sessions with no tracks
        mock_container.session_repository.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_sessions_handles_error(self, mock_container, mock_settings):
        """Should handle errors during session resume gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.session_repository.get_all_active.side_effect = Exception("DB error")
        bot = MusicBot(container=mock_container, settings=mock_settings)

        # Should not raise
        await bot._resume_sessions()


# =============================================================================
# Cog Loading Tests
# =============================================================================


class TestLoadCogs:
    """Tests for MusicBot._load_cogs method."""

    @pytest.mark.asyncio
    async def test_load_cogs_loads_all_cogs(self, mock_container, mock_settings):
        """Should attempt to load all cogs."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load:
            await bot._load_cogs()

        expected_cogs = [
            "discord_music_player.infrastructure.discord.cogs.playback_cog",
            "discord_music_player.infrastructure.discord.cogs.queue_cog",
            "discord_music_player.infrastructure.discord.cogs.skip_cog",
            "discord_music_player.infrastructure.discord.cogs.radio_cog",
            "discord_music_player.infrastructure.discord.cogs.now_playing_cog",
            "discord_music_player.infrastructure.discord.cogs.admin_cog",
            "discord_music_player.infrastructure.discord.cogs.health_cog",
            "discord_music_player.infrastructure.discord.cogs.info_cog",
            "discord_music_player.infrastructure.discord.cogs.event_cog",
            "discord_music_player.infrastructure.discord.cogs.analytics_cog",
            "discord_music_player.infrastructure.discord.cogs.favorites_cog",
            "discord_music_player.infrastructure.discord.cogs.saved_queue_cog",
        ]

        assert mock_load.call_count == len(expected_cogs)
        for cog in expected_cogs:
            mock_load.assert_any_call(cog)

    @pytest.mark.asyncio
    async def test_load_cogs_handles_individual_failure(self, mock_container, mock_settings):
        """Should continue loading other cogs when one fails."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        async def load_side_effect(cog_name):
            if "playback_cog" in cog_name:
                raise Exception("Playback cog failed")

        with patch.object(
            bot, "load_extension", new_callable=AsyncMock, side_effect=load_side_effect
        ) as mock_load:
            await bot._load_cogs()

        # Should still attempt to load all cogs
        assert mock_load.call_count == 12


# =============================================================================
# Command Sync Tests
# =============================================================================


class TestSyncCommands:
    """Tests for MusicBot._sync_commands method."""

    @pytest.mark.asyncio
    async def test_sync_commands_global(self, mock_container, mock_settings):
        """Should sync commands globally."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(
            bot.tree, "sync", new_callable=AsyncMock, return_value=[MagicMock(), MagicMock()]
        ) as mock_sync:
            await bot._sync_commands()

            mock_sync.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_sync_commands_test_guilds(self, mock_container, mock_settings):
        """Should sync to test guilds when specified."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.test_guild_ids = [111111, 222222]
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(
            bot.tree, "sync", new_callable=AsyncMock, return_value=[MagicMock()]
        ) as mock_sync:
            await bot._sync_commands()

            # Should sync to each test guild
            assert mock_sync.call_count == 3  # 2 guilds + 1 global

    @pytest.mark.asyncio
    async def test_sync_commands_handles_guild_error(self, mock_container, mock_settings):
        """Should handle individual guild sync errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_settings.discord.test_guild_ids = [111111]
        bot = MusicBot(container=mock_container, settings=mock_settings)

        async def sync_side_effect(guild=None):
            if guild is not None:
                raise Exception("Guild sync failed")
            return []

        with patch.object(
            bot.tree, "sync", new_callable=AsyncMock, side_effect=sync_side_effect
        ) as mock_sync:
            # Should not raise
            await bot._sync_commands()

            # Should still attempt global sync
            mock_sync.assert_any_call()

    @pytest.mark.asyncio
    async def test_sync_commands_handles_global_error(self, mock_container, mock_settings):
        """Should handle global sync errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(
            bot.tree, "sync", new_callable=AsyncMock, side_effect=Exception("Global sync failed")
        ):
            # Should not raise
            await bot._sync_commands()


# =============================================================================
# App Command Error Handler Tests
# =============================================================================


class TestAppCommandErrorHandler:
    """Tests for MusicBot._on_app_command_error method."""

    @pytest.mark.asyncio
    async def test_error_handler_sends_ephemeral_response(self, mock_container, mock_settings):
        """Should send ephemeral error message."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.command.name = "test_command"

        error = Exception("Test error")

        await bot._on_app_command_error(interaction, error)

        interaction.response.send_message.assert_called_once()
        call_args = interaction.response.send_message.call_args
        assert call_args.kwargs["ephemeral"] is True
        assert "Test error" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_error_handler_uses_followup_when_responded(self, mock_container, mock_settings):
        """Should use followup when interaction already responded."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        interaction = MagicMock()
        interaction.response.is_done.return_value = True
        interaction.followup.send = AsyncMock()
        interaction.command.name = "test_command"

        error = Exception("Test error")

        await bot._on_app_command_error(interaction, error)

        interaction.followup.send.assert_called_once()
        call_args = interaction.followup.send.call_args
        assert call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_error_handler_extracts_original_error(self, mock_container, mock_settings):
        """Should extract original error from wrapper."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock()
        interaction.command.name = "test_command"

        # Wrapped error
        original = ValueError("Original error")
        wrapper = MagicMock(spec=discord.app_commands.CommandInvokeError)
        wrapper.original = original

        await bot._on_app_command_error(interaction, wrapper)

        call_args = interaction.response.send_message.call_args
        assert "Original error" in call_args.args[0]

    @pytest.mark.asyncio
    async def test_error_handler_handles_send_failure(self, mock_container, mock_settings):
        """Should handle failure to send error message gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        interaction = MagicMock()
        interaction.response.is_done.return_value = False
        interaction.response.send_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Send failed")
        )
        interaction.command.name = "test_command"

        error = Exception("Test error")

        # Should not raise
        await bot._on_app_command_error(interaction, error)


# =============================================================================
# On Ready Handler Tests
# =============================================================================


class TestOnReady:
    """Tests for MusicBot.on_ready event handler."""

    @pytest.mark.asyncio
    async def test_on_ready_sets_presence(self, mock_container, mock_settings):
        """Should set bot presence on ready."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        # Mock the user and guilds properties
        mock_user = MagicMock()
        mock_user.id = 123456789

        with patch.object(type(bot), "user", PropertyMock(return_value=mock_user)):
            with patch.object(
                type(bot), "guilds", PropertyMock(return_value=[MagicMock(), MagicMock()])
            ):
                with patch.object(bot, "change_presence", new_callable=AsyncMock) as mock_change:
                    await bot.on_ready()

                    mock_change.assert_called_once()
                    call_args = mock_change.call_args
                    activity = call_args.kwargs["activity"]
                    assert activity.type == discord.ActivityType.listening
                    assert activity.name == "/play"


# =============================================================================
# Close/Shutdown Tests
# =============================================================================


class TestBotClose:
    """Tests for MusicBot.close method."""

    @pytest.mark.asyncio
    async def test_close_stops_cleanup_job(self, mock_container, mock_settings):
        """Should stop cleanup job on close."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[])):
            await bot.close()

        mock_container.cleanup_job.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_disconnects_voice_clients(self, mock_container, mock_settings):
        """Should disconnect all voice clients on close."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        vc1 = AsyncMock()
        vc2 = AsyncMock()

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[vc1, vc2])):
            await bot.close()

        vc1.disconnect.assert_called_once_with(force=True)
        vc2.disconnect.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_close_handles_voice_disconnect_error(self, mock_container, mock_settings):
        """Should handle voice disconnect errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        vc = AsyncMock()
        vc.disconnect.side_effect = Exception("Disconnect failed")

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[vc])):
            # Should not raise
            await bot.close()

    @pytest.mark.asyncio
    async def test_close_shuts_down_container(self, mock_container, mock_settings):
        """Should shutdown container on close."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[])):
            await bot.close()

        mock_container.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_handles_container_shutdown_error(self, mock_container, mock_settings):
        """Should handle container shutdown errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.shutdown.side_effect = Exception("Shutdown failed")
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[])):
            # Should not raise
            await bot.close()

    @pytest.mark.asyncio
    async def test_close_handles_cleanup_stop_error(self, mock_container, mock_settings):
        """Should handle cleanup job stop errors gracefully."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        mock_container.cleanup_job.stop.side_effect = Exception("Stop failed")
        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[])):
            # Should not raise
            await bot.close()

    @pytest.mark.asyncio
    async def test_close_sets_shutdown_event(self, mock_container, mock_settings):
        """Should set shutdown event on close."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(type(bot), "voice_clients", PropertyMock(return_value=[])):
            await bot.close()

        assert bot._shutdown_event.is_set()


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestCreateBot:
    """Tests for create_bot factory function."""

    def test_create_bot_returns_music_bot(self, mock_container, mock_settings):
        """Should return MusicBot instance."""
        from discord_music_player.infrastructure.discord.bot import MusicBot, create_bot

        bot = create_bot(container=mock_container, settings=mock_settings)

        assert isinstance(bot, MusicBot)

    def test_create_bot_passes_arguments(self, mock_container, mock_settings):
        """Should pass container and settings to MusicBot."""
        from discord_music_player.infrastructure.discord.bot import create_bot

        bot = create_bot(container=mock_container, settings=mock_settings)

        assert bot.container is mock_container
        assert bot.settings is mock_settings


# =============================================================================
# Session Recovery Tests
# =============================================================================


def _make_session(
    guild_id: int = 123456,
    state: str = "playing",
    with_track: bool = True,
    queue_count: int = 0,
) -> "GuildPlaybackSession":
    """Helper to build a GuildPlaybackSession for testing."""
    from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
    from discord_music_player.domain.music.enums import PlaybackState
    from discord_music_player.domain.music.wrappers import TrackId

    session = GuildPlaybackSession(guild_id=guild_id)
    session.state = PlaybackState(state)

    if with_track:
        session.current_track = Track(
            id=TrackId(value="test_id"),
            title="Test Track",
            webpage_url="https://youtube.com/watch?v=test_id",
        )

    for i in range(queue_count):
        session.queue.append(
            Track(
                id=TrackId(value=f"q{i}"),
                title=f"Queue Track {i}",
                webpage_url=f"https://youtube.com/watch?v=q{i}",
            )
        )

    return session


def _make_guild_mock(
    guild_id: int = 123456,
    voice_channels: list[MagicMock] | None = None,
    text_channels: list[MagicMock] | None = None,
    system_channel: MagicMock | None = None,
) -> MagicMock:
    """Helper to build a mock discord.Guild."""
    guild = MagicMock(spec=discord.Guild)
    guild.id = guild_id
    guild.voice_channels = voice_channels or []
    guild.text_channels = text_channels or []
    guild.system_channel = system_channel
    guild.me = MagicMock()
    return guild


def _make_voice_channel(members_bot_flags: list[bool] | None = None) -> MagicMock:
    """Create a mock voice channel. members_bot_flags is a list of is_bot values."""
    vc = MagicMock(spec=discord.VoiceChannel)
    vc.id = 999
    if members_bot_flags is None:
        members_bot_flags = []
    members = []
    for is_bot in members_bot_flags:
        m = MagicMock()
        m.bot = is_bot
        members.append(m)
    vc.members = members
    return vc


def _make_text_channel(can_send: bool = True) -> MagicMock:
    """Create a mock text channel."""
    tc = MagicMock(spec=discord.TextChannel)
    tc.id = 888
    tc.send = AsyncMock()
    perms = MagicMock()
    perms.send_messages = can_send
    tc.permissions_for = MagicMock(return_value=perms)
    return tc


class TestFindTextChannel:
    """Tests for MusicBot._find_text_channel static method."""

    def test_returns_system_channel_if_present(self, mock_container, mock_settings):
        """Should return guild system_channel when it exists and is a TextChannel."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        sys_channel = _make_text_channel()
        guild = _make_guild_mock(system_channel=sys_channel)
        # system_channel needs to pass isinstance check
        type(guild).system_channel = PropertyMock(return_value=sys_channel)

        result = MusicBot._find_text_channel(guild)
        assert result is sys_channel

    def test_falls_back_to_first_sendable_channel(self, mock_container, mock_settings):
        """Should return first sendable text channel when no system_channel."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        guild = _make_guild_mock(system_channel=None)
        no_send = _make_text_channel(can_send=False)
        can_send = _make_text_channel(can_send=True)
        guild.text_channels = [no_send, can_send]

        result = MusicBot._find_text_channel(guild)
        assert result is can_send

    def test_returns_none_when_no_channels(self, mock_container, mock_settings):
        """Should return None when no suitable text channel found."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        guild = _make_guild_mock(system_channel=None)
        guild.text_channels = []

        result = MusicBot._find_text_channel(guild)
        assert result is None

    def test_returns_none_when_no_sendable_channels(self, mock_container, mock_settings):
        """Should return None when all channels lack send permissions."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        guild = _make_guild_mock(system_channel=None)
        no_send = _make_text_channel(can_send=False)
        guild.text_channels = [no_send]

        result = MusicBot._find_text_channel(guild)
        assert result is None


class TestFindResumableVoiceChannel:
    """Tests for MusicBot._find_resumable_voice_channel static method."""

    def test_finds_channel_with_non_bot_member(self, mock_container, mock_settings):
        """Should return first voice channel with a human member."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        vc_bots_only = _make_voice_channel([True, True])
        vc_with_human = _make_voice_channel([True, False])
        guild = _make_guild_mock(voice_channels=[vc_bots_only, vc_with_human])

        result = MusicBot._find_resumable_voice_channel(guild)
        assert result is vc_with_human

    def test_returns_none_when_all_bots(self, mock_container, mock_settings):
        """Should return None when all voice channel members are bots."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        vc = _make_voice_channel([True, True])
        guild = _make_guild_mock(voice_channels=[vc])

        result = MusicBot._find_resumable_voice_channel(guild)
        assert result is None

    def test_returns_none_when_no_voice_channels(self, mock_container, mock_settings):
        """Should return None when guild has no voice channels."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        guild = _make_guild_mock(voice_channels=[])

        result = MusicBot._find_resumable_voice_channel(guild)
        assert result is None

    def test_returns_none_when_channels_empty(self, mock_container, mock_settings):
        """Should return None when voice channels have no members."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        vc = _make_voice_channel([])
        guild = _make_guild_mock(voice_channels=[vc])

        result = MusicBot._find_resumable_voice_channel(guild)
        assert result is None


class TestResetSession:
    """Tests for MusicBot._reset_session method."""

    @pytest.mark.asyncio
    async def test_resets_state_to_idle(self, mock_container, mock_settings):
        """Should set session state to IDLE and clear current track."""
        from discord_music_player.domain.music.enums import PlaybackState
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        session = _make_session(state="playing", with_track=True)
        repo = AsyncMock()

        await bot._reset_session(session, repo)

        assert session.state == PlaybackState.IDLE
        assert session.current_track is None
        repo.save.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_saves_session_via_repository(self, mock_container, mock_settings):
        """Should persist the reset session."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        session = _make_session(state="paused", with_track=False)
        repo = AsyncMock()

        await bot._reset_session(session, repo)

        repo.save.assert_called_once_with(session)


class TestTryResumeSession:
    """Tests for MusicBot._try_resume_session method."""

    @pytest.mark.asyncio
    async def test_resets_message_state(self, mock_container, mock_settings):
        """Should call message_state_manager.reset for the guild."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()

        session = _make_session(with_track=False)
        guild = _make_guild_mock()

        await bot._try_resume_session(session, guild)

        mock_container.message_state_manager.reset.assert_called_once_with(session.guild_id)

    @pytest.mark.asyncio
    async def test_returns_false_when_no_tracks(self, mock_container, mock_settings):
        """Should return False when session has no tracks."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()

        session = _make_session(with_track=False, queue_count=0)
        guild = _make_guild_mock()

        result = await bot._try_resume_session(session, guild)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_voice_channel(self, mock_container, mock_settings):
        """Should return False when no voice channel has human members."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()

        session = _make_session(with_track=True)
        guild = _make_guild_mock(voice_channels=[])

        result = await bot._try_resume_session(session, guild)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_text_channel(self, mock_container, mock_settings):
        """Should return False when no suitable text channel found."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()

        session = _make_session(with_track=True)
        vc = _make_voice_channel([False])
        guild = _make_guild_mock(voice_channels=[vc], text_channels=[], system_channel=None)

        result = await bot._try_resume_session(session, guild)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_voice_connect_fails(self, mock_container, mock_settings):
        """Should return False when voice adapter fails to connect."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()
        mock_container.voice_adapter = MagicMock()
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=False)

        session = _make_session(with_track=True)
        vc = _make_voice_channel([False])
        tc = _make_text_channel()
        guild = _make_guild_mock(
            voice_channels=[vc], text_channels=[tc], system_channel=tc,
        )

        result = await bot._try_resume_session(session, guild)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_on_successful_resume(self, mock_container, mock_settings):
        """Should return True when all steps succeed."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock()
        mock_container.voice_adapter = MagicMock()
        mock_container.voice_adapter.ensure_connected = AsyncMock(return_value=True)
        mock_container.playback_service = MagicMock()

        session = _make_session(with_track=True)
        vc = _make_voice_channel([False])
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())
        guild = _make_guild_mock(
            voice_channels=[vc], text_channels=[tc], system_channel=tc,
        )

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view = MagicMock()
            mock_view_cls.return_value = mock_view
            result = await bot._try_resume_session(session, guild)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_exception(self, mock_container, mock_settings):
        """Should return False and not raise when an exception occurs."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.message_state_manager = MagicMock()
        mock_container.message_state_manager.reset = AsyncMock(
            side_effect=Exception("boom")
        )

        session = _make_session(with_track=True)
        guild = _make_guild_mock()

        result = await bot._try_resume_session(session, guild)
        assert result is False


def _make_mock_session(
    guild_id: int = 123456,
    current_track_title: str | None = "Test Track",
    queue_titles: list[str] | None = None,
    prepare_for_resume_return: int = 0,
) -> MagicMock:
    """Build a MagicMock session for _send_resume_prompt tests (avoids Pydantic __setattr__)."""
    session = MagicMock()
    session.guild_id = guild_id
    session.prepare_for_resume = MagicMock(return_value=prepare_for_resume_return)

    if current_track_title is not None:
        track = MagicMock()
        track.title = current_track_title
        session.current_track = track
    else:
        session.current_track = None

    if queue_titles:
        session.queue = [MagicMock(title=t) for t in queue_titles]
    else:
        session.queue = []

    return session


class TestSendResumePrompt:
    """Tests for MusicBot._send_resume_prompt method."""

    @pytest.mark.asyncio
    async def test_calls_prepare_for_resume_and_saves(self, mock_container, mock_settings):
        """Should call prepare_for_resume on session and save it."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session()
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ):
            await bot._send_resume_prompt(session, tc)

        session.prepare_for_resume.assert_called_once()
        mock_container.session_repository.save.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_creates_resume_view_with_correct_args(self, mock_container, mock_settings):
        """Should create ResumePlaybackView with guild_id, channel_id, and track title."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session()
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view_cls.return_value = MagicMock()
            await bot._send_resume_prompt(session, tc)

        mock_view_cls.assert_called_once()
        call_kwargs = mock_view_cls.call_args.kwargs
        assert call_kwargs["guild_id"] == session.guild_id
        assert call_kwargs["channel_id"] == tc.id
        assert call_kwargs["track_title"] == "Test Track"
        assert call_kwargs["playback_service"] is mock_container.playback_service

    @pytest.mark.asyncio
    async def test_sends_message_with_track_title(self, mock_container, mock_settings):
        """Should send a message containing the track title."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session()
        tc = _make_text_channel()
        mock_message = MagicMock()
        tc.send = AsyncMock(return_value=mock_message)

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view = MagicMock()
            mock_view_cls.return_value = mock_view
            await bot._send_resume_prompt(session, tc)

        tc.send.assert_called_once()
        sent_text = tc.send.call_args.args[0]
        assert "Test Track" in sent_text
        mock_view.set_message.assert_called_once_with(mock_message)

    @pytest.mark.asyncio
    async def test_includes_timestamp_when_elapsed(self, mock_container, mock_settings):
        """Should include timestamp label when elapsed seconds > 0."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session(prepare_for_resume_return=125)
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view_cls.return_value = MagicMock()
            await bot._send_resume_prompt(session, tc)

        sent_text = tc.send.call_args.args[0]
        assert "2:05" in sent_text

    @pytest.mark.asyncio
    async def test_uses_queue_title_when_no_current_track(self, mock_container, mock_settings):
        """Should fall back to first queue track title when current_track is None."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session(
            current_track_title=None,
            queue_titles=["Queue Track 0", "Queue Track 1"],
        )
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view_cls.return_value = MagicMock()
            await bot._send_resume_prompt(session, tc)

        sent_text = tc.send.call_args.args[0]
        assert "Queue Track 0" in sent_text

    @pytest.mark.asyncio
    async def test_uses_unknown_when_no_tracks_at_all(self, mock_container, mock_settings):
        """Should use 'Unknown' when neither current_track nor queue has tracks."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)
        mock_container.playback_service = MagicMock()

        session = _make_mock_session(current_track_title=None, queue_titles=None)
        tc = _make_text_channel()
        tc.send = AsyncMock(return_value=MagicMock())

        with patch(
            "discord_music_player.infrastructure.discord.bot.ResumePlaybackView"
        ) as mock_view_cls:
            mock_view_cls.return_value = MagicMock()
            await bot._send_resume_prompt(session, tc)

        sent_text = tc.send.call_args.args[0]
        assert "Unknown" in sent_text


class TestResumeSessionsIntegration:
    """Integration-level tests for _resume_sessions orchestration."""

    @pytest.mark.asyncio
    async def test_resumes_session_when_guild_found_and_resumable(
        self, mock_container, mock_settings
    ):
        """Should call _try_resume_session when guild is found."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session = _make_session(state="playing", with_track=True)
        mock_container.session_repository.get_all_active.return_value = [session]

        bot = MusicBot(container=mock_container, settings=mock_settings)

        guild = _make_guild_mock(guild_id=session.guild_id)

        with patch.object(bot, "get_guild", return_value=guild):
            with patch.object(
                bot, "_try_resume_session", new_callable=AsyncMock, return_value=True
            ) as mock_try:
                await bot._resume_sessions()

        mock_try.assert_called_once_with(session, guild)

    @pytest.mark.asyncio
    async def test_resets_when_try_resume_fails(self, mock_container, mock_settings):
        """Should reset session when _try_resume_session returns False."""
        from discord_music_player.domain.music.enums import PlaybackState
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session = _make_session(state="playing", with_track=True)
        mock_container.session_repository.get_all_active.return_value = [session]

        bot = MusicBot(container=mock_container, settings=mock_settings)

        guild = _make_guild_mock(guild_id=session.guild_id)

        with patch.object(bot, "get_guild", return_value=guild):
            with patch.object(
                bot, "_try_resume_session", new_callable=AsyncMock, return_value=False
            ):
                await bot._resume_sessions()

        assert session.state == PlaybackState.IDLE
        assert session.current_track is None
        mock_container.session_repository.save.assert_called_once_with(session)

    @pytest.mark.asyncio
    async def test_skips_idle_empty_sessions(self, mock_container, mock_settings):
        """Should skip sessions that are IDLE with no tracks."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session = _make_session(state="idle", with_track=False, queue_count=0)
        mock_container.session_repository.get_all_active.return_value = [session]

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "get_guild") as mock_get_guild:
            await bot._resume_sessions()

        mock_get_guild.assert_not_called()
        mock_container.session_repository.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_skip_idle_session_with_queue(self, mock_container, mock_settings):
        """Should NOT skip idle sessions that still have tracks in queue."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session = _make_session(state="idle", with_track=False, queue_count=3)
        mock_container.session_repository.get_all_active.return_value = [session]

        bot = MusicBot(container=mock_container, settings=mock_settings)
        guild = _make_guild_mock(guild_id=session.guild_id)

        with patch.object(bot, "get_guild", return_value=guild):
            with patch.object(
                bot, "_try_resume_session", new_callable=AsyncMock, return_value=True
            ) as mock_try:
                await bot._resume_sessions()

        mock_try.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_multiple_sessions(self, mock_container, mock_settings):
        """Should process multiple sessions independently."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        session1 = _make_session(guild_id=111, state="playing", with_track=True)
        session2 = _make_session(guild_id=222, state="playing", with_track=True)
        mock_container.session_repository.get_all_active.return_value = [session1, session2]

        bot = MusicBot(container=mock_container, settings=mock_settings)

        guild1 = _make_guild_mock(guild_id=111)
        guild2 = _make_guild_mock(guild_id=222)

        def get_guild_side_effect(gid: int) -> MagicMock | None:
            return {111: guild1, 222: guild2}.get(gid)

        with patch.object(bot, "get_guild", side_effect=get_guild_side_effect):
            with patch.object(
                bot, "_try_resume_session", new_callable=AsyncMock, return_value=True
            ) as mock_try:
                await bot._resume_sessions()

        assert mock_try.call_count == 2
