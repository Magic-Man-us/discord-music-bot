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
    async def test_setup_hook_resets_stale_sessions(self, mock_container, mock_settings):
        """Should reset stale sessions during setup."""
        from discord_music_player.infrastructure.discord.bot import MusicBot

        bot = MusicBot(container=mock_container, settings=mock_settings)

        with patch.object(bot, "_load_cogs", new_callable=AsyncMock):
            with patch.object(bot, "_resume_sessions", new_callable=AsyncMock) as mock_reset:
                await bot.setup_hook()

        mock_reset.assert_called_once()

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
    async def test_resume_sessions_resets_when_guild_not_found(
        self, mock_container, mock_settings
    ):
        """Should reset sessions when guild is not found."""
        from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
        from discord_music_player.domain.music.value_objects import PlaybackState, TrackId
        from discord_music_player.infrastructure.discord.bot import MusicBot

        # Create session with current track
        session = GuildPlaybackSession(guild_id=123456)
        session.current_track = Track(
            id=TrackId("test"),
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
        from discord_music_player.domain.music.value_objects import PlaybackState
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
            "discord_music_player.infrastructure.discord.cogs.music_cog",
            "discord_music_player.infrastructure.discord.cogs.admin_cog",
            "discord_music_player.infrastructure.discord.cogs.health_cog",
            "discord_music_player.infrastructure.discord.cogs.info_cog",
            "discord_music_player.infrastructure.discord.cogs.event_cog",
            "discord_music_player.infrastructure.discord.cogs.analytics_cog",
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
            if "music_cog" in cog_name:
                raise Exception("Music cog failed")

        with patch.object(
            bot, "load_extension", new_callable=AsyncMock, side_effect=load_side_effect
        ) as mock_load:
            await bot._load_cogs()

        # Should still attempt to load all cogs
        assert mock_load.call_count == 6


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
        wrapper = MagicMock()
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
