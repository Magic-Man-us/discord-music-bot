"""Main Discord bot class integrating the DI container, cog lifecycle, and background jobs."""

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
    def __init__(
        self,
        container: Container,
        settings: Settings,
        **kwargs,
    ) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.members = True

        super().__init__(
            command_prefix=settings.discord.command_prefix,
            intents=intents,
            help_command=None,
            **kwargs,
        )

        self.container = container
        self.settings = settings
        self._shutdown_event = asyncio.Event()
        container.set_bot(self)

    async def setup_hook(self) -> None:
        logger.info(LogTemplates.BOT_SETUP)

        try:
            await self.container.initialize()
            logger.info(LogTemplates.BOT_CONTAINER_INITIALIZED)
        except Exception as e:
            logger.exception(LogTemplates.BOT_CONTAINER_INIT_FAILED, e)
            raise

        await self._resume_sessions()
        await self._load_cogs()
        self.tree.on_error = self._on_app_command_error

        try:
            cleanup_job = self.container.cleanup_job
            cleanup_job.start()
            logger.info(LogTemplates.CLEANUP_STARTED)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CLEANUP_START_FAILED, e)

        if self.settings.discord.sync_on_startup:
            try:
                await self._sync_commands()
            except Exception as e:
                logger.warning(LogTemplates.BOT_SYNC_ON_STARTUP_FAILED, e)

        logger.info(LogTemplates.BOT_SETUP_COMPLETE)

    async def _resume_sessions(self) -> None:
        """Resume playback sessions that were active before bot restart."""
        try:
            from ...domain.music.value_objects import PlaybackState

            session_repo = self.container.session_repository
            sessions = await session_repo.get_all_active()

            resumed_count = 0
            reset_count = 0

            for session in sessions:
                # Skip sessions that are already idle with no tracks
                if session.state == PlaybackState.IDLE and not session.has_tracks:
                    continue

                guild = self.get_guild(session.guild_id)
                if guild is None:
                    logger.debug(
                        "Guild %s not found, resetting session", session.guild_id
                    )
                    await self._reset_session(session, session_repo)
                    reset_count += 1
                    continue

                # Try to resume this session
                if await self._try_resume_session(session, guild):
                    resumed_count += 1
                else:
                    await self._reset_session(session, session_repo)
                    reset_count += 1

            if resumed_count > 0:
                logger.info("Resumed %d playback session(s)", resumed_count)
            if reset_count > 0:
                logger.info("Reset %d stale session(s)", reset_count)

        except Exception as e:
            logger.warning(LogTemplates.BOT_STALE_SESSIONS_RESET_FAILED, e)

    async def _try_resume_session(
        self, session: any, guild: discord.Guild
    ) -> bool:
        """Attempt to resume playback for a single session. Returns True if successful."""
        try:
            # Skip if no tracks to play
            if not session.has_tracks:
                logger.debug("Session %s has no tracks, skipping resume", session.guild_id)
                return False

            # Find a voice channel with members
            voice_channel = await self._find_resumable_voice_channel(guild)
            if voice_channel is None:
                logger.debug(
                    "No suitable voice channel found for guild %s", session.guild_id
                )
                return False

            # Find a text channel to post the resume prompt
            text_channel = await self._find_text_channel(guild, session)
            if text_channel is None:
                logger.debug(
                    "No text channel found for guild %s, skipping resume", session.guild_id
                )
                return False

            # Connect to voice first
            voice_adapter = self.container.voice_adapter
            success = await voice_adapter.ensure_connected(
                session.guild_id, voice_channel.id
            )
            if not success:
                logger.debug(
                    "Failed to connect to voice in guild %s", session.guild_id
                )
                return False

            # Determine what track to show in the prompt
            track_title = "Unknown"
            if session.current_track is not None:
                track_title = session.current_track.title
            elif session.queue:
                track_title = session.queue[0].title

            # Send resume prompt to channel
            from .views.resume_playback_view import ResumePlaybackView

            playback_service = self.container.playback_service
            view = ResumePlaybackView(
                guild_id=session.guild_id,
                channel_id=text_channel.id,
                playback_service=playback_service,
                track_title=track_title,
            )

            message = await text_channel.send(
                f"🔄 I was playing **{track_title}** before restarting. Resume playback?",
                view=view,
            )
            view.set_message(message)

            logger.info(
                "Sent resume prompt for guild %s: %s",
                session.guild_id,
                track_title,
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to resume session for guild %s: %s", session.guild_id, e
            )
            return False

    async def _find_text_channel(
        self, guild: discord.Guild, session: any
    ) -> discord.TextChannel | None:
        """Find a suitable text channel to post the resume prompt."""
        # Try system channel first
        if guild.system_channel and isinstance(guild.system_channel, discord.TextChannel):
            return guild.system_channel

        # Try first text channel bot can send to
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel

        return None

    async def _find_resumable_voice_channel(
        self, guild: discord.Guild
    ) -> discord.VoiceChannel | None:
        """Find a voice channel with at least one non-bot member."""
        for channel in guild.voice_channels:
            # Count non-bot members
            member_count = sum(1 for m in channel.members if not m.bot)
            if member_count > 0:
                return channel
        return None

    async def _reset_session(self, session: any, session_repo: any) -> None:
        """Reset a session to IDLE state."""
        from ...domain.music.value_objects import PlaybackState

        session.state = PlaybackState.IDLE
        session.current_track = None
        await session_repo.save(session)

    async def _load_cogs(self) -> None:
        cogs = [
            "discord_music_player.infrastructure.discord.cogs.music_cog",
            "discord_music_player.infrastructure.discord.cogs.admin_cog",
            "discord_music_player.infrastructure.discord.cogs.health_cog",
            "discord_music_player.infrastructure.discord.cogs.info_cog",
            "discord_music_player.infrastructure.discord.cogs.event_cog",
            "discord_music_player.infrastructure.discord.cogs.analytics_cog",
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
        """Global slash-command error handler; sends ephemeral messages to avoid channel spam."""
        original = getattr(error, "original", error)

        logger.error(
            LogTemplates.BOT_SLASH_COMMAND_ERROR,
            getattr(interaction.command, "name", "<unknown>"),
            original,
        )

        error_msg = f"❌ An error occurred: {original}"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True)
        except discord.HTTPException:
            logger.warning(LogTemplates.BOT_ERROR_MESSAGE_SEND_FAILED)

    async def _sync_commands(self) -> None:
        test_guilds = self.settings.discord.test_guild_ids

        if test_guilds:
            for guild_id in test_guilds:
                guild = discord.Object(id=guild_id)
                try:
                    synced = await self.tree.sync(guild=guild)
                    logger.info(LogTemplates.BOT_SYNCED_GUILD, len(synced), guild_id)
                except Exception as e:
                    logger.warning(LogTemplates.BOT_SYNC_GUILD_FAILED, guild_id, e)

        try:
            synced = await self.tree.sync()
            logger.info(LogTemplates.BOT_SYNCED_GLOBAL, len(synced))
        except Exception as e:
            logger.warning(LogTemplates.BOT_SYNC_GLOBAL_FAILED, e)

    async def on_ready(self) -> None:
        logger.info(
            LogTemplates.BOT_READY,
            self.user,  # type: ignore
            self.user.id,  # type: ignore
        )
        logger.info(LogTemplates.BOT_CONNECTED_GUILDS, len(self.guilds))

        activity = discord.Activity(type=discord.ActivityType.listening, name="/play")
        await self.change_presence(activity=activity)

    async def close(self) -> None:
        logger.info(LogTemplates.BOT_SHUTTING_DOWN)

        try:
            cleanup_job = self.container.cleanup_job
            await cleanup_job.stop()
            logger.info(LogTemplates.CLEANUP_STOPPED)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CLEANUP_STOP_ERROR, e)

        for vc in self.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

        try:
            await self.container.shutdown()
            logger.info(LogTemplates.BOT_CONTAINER_SHUTDOWN)
        except Exception as e:
            logger.warning(LogTemplates.BOT_CONTAINER_SHUTDOWN_ERROR, e)

        await super().close()
        self._shutdown_event.set()
        logger.info(LogTemplates.BOT_SHUTDOWN_COMPLETE)

    def run_with_graceful_shutdown(self, token: str, *, shutdown_timeout: float = 30.0) -> None:
        async def runner():
            async with self:
                loop = asyncio.get_running_loop()

                async def _graceful_close() -> None:
                    try:
                        await asyncio.wait_for(self.close(), timeout=shutdown_timeout)
                    except TimeoutError:
                        logger.warning(LogTemplates.BOT_SHUTDOWN_TIMEOUT, shutdown_timeout)

                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, lambda: asyncio.create_task(_graceful_close()))
                await self.start(token)

        asyncio.run(runner())


def create_bot(container: Container, settings: Settings) -> MusicBot:
    return MusicBot(container=container, settings=settings)
