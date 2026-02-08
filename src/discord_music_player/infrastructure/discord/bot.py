"""
Discord Music Bot Implementation

The main Discord bot class that integrates the dependency injection container,
manages cog lifecycle, handles graceful shutdown, and coordinates background jobs.
This is the infrastructure layer's entry point for the Discord.py framework.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...config.container import Container
    from ...config.settings import Settings

logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    """Discord music bot with DDD architecture.

    This bot integrates the DI container and handles:
    - Command prefix and slash commands
    - Cog loading and management
    - Graceful shutdown with cleanup
    - Background job management
    """

    def __init__(
        self,
        container: Container,
        settings: Settings,
        **kwargs,
    ) -> None:
        """Initialize the music bot.

        Args:
            container: The dependency injection container.
            settings: Application settings.
            **kwargs: Additional arguments for commands.Bot.
        """
        # Set up intents
        intents = discord.Intents.default()
        intents.message_content = True  # For prefix commands
        intents.voice_states = True  # For voice channel tracking
        intents.guilds = True  # For guild events
        intents.members = True  # For member events (if enabled)

        # Initialize the bot
        super().__init__(
            command_prefix=settings.discord.command_prefix,
            intents=intents,
            help_command=None,  # We'll use our own or slash commands
            **kwargs,
        )

        self.container = container
        self.settings = settings
        self._shutdown_event = asyncio.Event()

        # Set the bot reference in the container
        container.set_bot(self)

    async def setup_hook(self) -> None:
        """Called when the bot is starting up.

        This is where we:
        - Initialize the database
        - Load cogs
        - Start background jobs
        - Sync slash commands (optionally)
        """
        logger.info(LogTemplates.BOT_SETUP)

        # Initialize the container (database, etc.)
        try:
            await self.container.initialize()
            logger.info(LogTemplates.BOT_CONTAINER_INITIALIZED)
        except Exception as e:
            logger.exception(LogTemplates.BOT_CONTAINER_INIT_FAILED, e)
            raise

        # Reset all stale sessions from previous runs
        # This prevents issues where bot thinks it's still playing from last run
        await self._reset_stale_sessions()

        # Load cogs
        await self._load_cogs()

        # Set up global slash command error handler
        self.tree.on_error = self._on_app_command_error

        # Start cleanup job
        try:
            cleanup_job = self.container.cleanup_job
            cleanup_job.start()
            logger.info(LogTemplates.CLEANUP_STARTED)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CLEANUP_START_FAILED, e)

        # Optionally sync commands on startup
        if self.settings.discord.sync_on_startup:
            try:
                await self._sync_commands()
            except Exception as e:
                logger.warning(LogTemplates.BOT_SYNC_ON_STARTUP_FAILED, e)

        logger.info(LogTemplates.BOT_SETUP_COMPLETE)

    async def _reset_stale_sessions(self) -> None:
        """Reset all sessions to IDLE state on startup.

        This prevents stale state from previous bot runs where
        the database thinks a track is still playing.
        """
        try:
            from ...domain.music.value_objects import PlaybackState

            session_repo = self.container.session_repository
            sessions = await session_repo.get_all_active()

            reset_count = 0
            for session in sessions:
                # Reset state to IDLE and clear current track
                if session.state != PlaybackState.IDLE or session.current_track is not None:
                    session.state = PlaybackState.IDLE
                    session.current_track = None
                    await session_repo.save(session)
                    reset_count += 1

            if reset_count > 0:
                logger.info(LogTemplates.BOT_STALE_SESSIONS_RESET, reset_count)
            else:
                logger.debug(LogTemplates.BOT_NO_STALE_SESSIONS)
        except Exception as e:
            logger.warning(LogTemplates.BOT_STALE_SESSIONS_RESET_FAILED, e)

    async def _load_cogs(self) -> None:
        """Load all cogs from the new architecture."""
        cogs = [
            "discord_music_player.infrastructure.discord.cogs.music_cog",
            "discord_music_player.infrastructure.discord.cogs.admin_cog",
            "discord_music_player.infrastructure.discord.cogs.health_cog",
            "discord_music_player.infrastructure.discord.cogs.info_cog",
            "discord_music_player.infrastructure.discord.cogs.event_cog",
        ]

        loaded = 0
        failed = 0

        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(LogTemplates.BOT_COG_LOADED, cog)
                loaded += 1
            except Exception as e:
                logger.exception(LogTemplates.BOT_COG_LOAD_FAILED, cog, e)
                failed += 1

        logger.info(LogTemplates.BOT_COGS_LOADED_SUMMARY, loaded, failed)

    async def _on_app_command_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        """Global error handler for slash commands.

        All errors are sent as ephemeral messages to avoid spam in channels.

        Args:
            interaction: The Discord interaction.
            error: The error that occurred.
        """
        # Get the original error if wrapped
        original = getattr(error, "original", error)

        # Log the error
        logger.error(
            LogTemplates.BOT_SLASH_COMMAND_ERROR,
            getattr(interaction.command, "name", "<unknown>"),
            original,
        )

        # Prepare error message
        error_msg = f"❌ An error occurred: {original}"

        # Try to send ephemeral response
        try:
            if interaction.response.is_done():
                # Already responded, use followup
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                # Haven't responded yet
                await interaction.response.send_message(error_msg, ephemeral=True)
        except discord.HTTPException:
            # Failed to send error message, just log it
            logger.warning(LogTemplates.BOT_ERROR_MESSAGE_SEND_FAILED)

    async def _sync_commands(self) -> None:
        """Sync slash commands with Discord."""
        # Sync to test guilds first if specified
        test_guilds = self.settings.discord.test_guild_ids

        if test_guilds:
            for guild_id in test_guilds:
                guild = discord.Object(id=guild_id)
                try:
                    synced = await self.tree.sync(guild=guild)
                    logger.info(LogTemplates.BOT_SYNCED_GUILD, len(synced), guild_id)
                except Exception as e:
                    logger.warning(LogTemplates.BOT_SYNC_GUILD_FAILED, guild_id, e)

        # Global sync
        try:
            synced = await self.tree.sync()
            logger.info(LogTemplates.BOT_SYNCED_GLOBAL, len(synced))
        except Exception as e:
            logger.warning(LogTemplates.BOT_SYNC_GLOBAL_FAILED, e)

    async def on_ready(self) -> None:
        """Called when the bot is ready and connected."""
        logger.info(
            LogTemplates.BOT_READY,
            self.user,  # type: ignore
            self.user.id,  # type: ignore
        )
        logger.info(LogTemplates.BOT_CONNECTED_GUILDS, len(self.guilds))

        # Set presence
        activity = discord.Activity(type=discord.ActivityType.listening, name="/play")
        await self.change_presence(activity=activity)

    async def close(self) -> None:
        """Gracefully close the bot and clean up resources."""
        logger.info(LogTemplates.BOT_SHUTTING_DOWN)

        # Stop cleanup job
        try:
            cleanup_job = self.container.cleanup_job
            await cleanup_job.stop()
            logger.info(LogTemplates.CLEANUP_STOPPED)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CLEANUP_STOP_ERROR, e)

        # Disconnect from voice channels
        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

        # Shutdown container (database, etc.)
        try:
            await self.container.shutdown()
            logger.info(LogTemplates.BOT_CONTAINER_SHUTDOWN)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CONTAINER_SHUTDOWN_ERROR, e)

        # Close the bot connection
        await super().close()

        # Signal shutdown complete
        self._shutdown_event.set()
        logger.info(LogTemplates.BOT_SHUTDOWN_COMPLETE)

    def run_with_graceful_shutdown(self, token: str) -> None:
        """Run the bot with graceful shutdown handling.

        Args:
            token: The Discord bot token.
        """

        async def runner():
            async with self:
                # Set up signal handlers
                loop = asyncio.get_running_loop()

                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, lambda: asyncio.create_task(self.close()))

                # Start the bot
                await self.start(token)

        asyncio.run(runner())


def create_bot(container: Container, settings: Settings) -> MusicBot:
    """Create a new music bot instance.

    Args:
        container: The dependency injection container.
        settings: Application settings.

    Returns:
        A configured MusicBot instance.
    """
    return MusicBot(container=container, settings=settings)
