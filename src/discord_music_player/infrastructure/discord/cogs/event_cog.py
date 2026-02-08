"""
Event Cog

Handles Discord events and provides logging functionality
using the DI container and new DDD architecture.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from discord_music_player.domain.shared.constants import ConfigKeys
from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class EventCog(commands.Cog):
    """Event handler cog for Discord events.

    Provides lightweight logging for common lifecycle, guild, member,
    message, and reaction events.
    """

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        """Initialize the event cog.

        Args:
            bot: The Discord bot instance.
            container: The DI container.
        """
        self.bot = bot
        self.container = container
        self._resumed_logged_once = False

        from ....domain.shared.events import get_event_bus

        self._event_bus = get_event_bus()

        # Get logging preferences from environment
        self._chat_logging = self._env_flag(ConfigKeys.LOG_EVENT_MESSAGES)
        self._reaction_logging = self._env_flag(ConfigKeys.LOG_EVENT_REACTIONS)

    @staticmethod
    def _env_flag(name: str) -> bool:
        """Check if an environment variable is a truthy flag."""
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_bot_or_none(user: discord.abc.User | discord.Member | None) -> bool:
        """Check if user is None or a bot account."""
        return user is None or bool(getattr(user, "bot", False))

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Called when the bot is ready."""
        logger.info("Bot ready as %s (%s)", self.bot.user, getattr(self.bot.user, "id", "?"))

    @commands.Cog.listener()
    async def on_connect(self) -> None:
        """Called when the bot connects to Discord."""
        logger.info("WebSocket connected")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        """Called when the bot disconnects from Discord."""
        logger.warning("WebSocket disconnected")

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        """Called when the bot resumes a session."""
        if not self._resumed_logged_once:
            logger.info("WebSocket session resumed")
            self._resumed_logged_once = True

    # ─────────────────────────────────────────────────────────────────
    # Guild Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Called when the bot joins a guild."""
        logger.info("Joined guild: %s (%s)", guild.name, guild.id)

        # Send welcome message if system channel exists
        if guild.system_channel:
            try:
                await guild.system_channel.send(DiscordUIMessages.SUCCESS_GUILD_WELCOME)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Called when the bot leaves a guild."""
        logger.info("Left guild: %s (%s)", guild.name, guild.id)

        # Clean up message state in MusicCog
        try:
            music_cog = self.bot.get_cog("MusicCog")
            if music_cog:
                cleanup_fn = getattr(music_cog, "cleanup_guild_message_state", None)
                if callable(cleanup_fn):
                    cleanup_fn(guild.id)
        except Exception:
            logger.debug("Could not cleanup music cog message state")

        # Clean up any sessions for this guild
        try:
            repo = self.container.session_repository
            await repo.delete(guild.id)
            logger.debug("Cleaned up session for guild %s", guild.id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Called when a guild is updated."""
        if before.name != after.name:
            logger.info("Guild renamed: %s -> %s", before.name, after.name)

    # ─────────────────────────────────────────────────────────────────
    # Member Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Called when a member joins a guild."""
        logger.info("Member joined: %s (%s) guild=%s", member, member.id, member.guild.id)

        # Send welcome in system channel
        ch = member.guild.system_channel
        if ch:
            try:
                await ch.send(
                    DiscordUIMessages.SUCCESS_MEMBER_WELCOME.format(member_mention=member.mention)
                )
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Called when a member leaves a guild."""
        logger.info(
            "Member left: %s (%s) guild=%s", member.display_name, member.id, member.guild.id
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        """Called when a user is banned from a guild."""
        logger.warning("User banned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        """Called when a user is unbanned from a guild."""
        logger.info("User unbanned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    # ─────────────────────────────────────────────────────────────────
    # Voice Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Called when a member's voice state changes.

        Handles auto-disconnect when the bot is alone in a voice channel.
        """
        if member.bot:
            return

        # Warmup gate: record joins/switches.
        joined_channel = after.channel is not None and (
            before.channel is None
            or (before.channel is not None and before.channel.id != after.channel.id)
        )
        if joined_channel and after.channel is not None:
            self.container.voice_warmup_tracker.mark_joined(
                guild_id=member.guild.id,
                user_id=member.id,
            )

            from ....domain.shared.events import VoiceMemberJoinedVoiceChannel

            await self._event_bus.publish(
                VoiceMemberJoinedVoiceChannel(
                    guild_id=member.guild.id,
                    channel_id=after.channel.id,
                    user_id=member.id,
                )
            )

        # Publish leave events for the bot-connected channel.
        bot_channel = self._get_bot_voice_channel(member.guild)
        left_channel = before.channel is not None and (
            after.channel is None
            or (after.channel is not None and after.channel.id != before.channel.id)
        )
        if (
            bot_channel is not None
            and left_channel
            and before.channel is not None
            and before.channel.id == bot_channel.id
        ):
            from ....domain.shared.events import VoiceMemberLeftVoiceChannel

            await self._event_bus.publish(
                VoiceMemberLeftVoiceChannel(
                    guild_id=member.guild.id,
                    channel_id=before.channel.id,
                    user_id=member.id,
                )
            )

        # Existing behavior: auto-disconnect when bot becomes alone.
        if not self._should_check_empty_channel(member, before):
            return

        bot_channel = self._get_bot_voice_channel(member.guild)
        if bot_channel is None or before.channel is None:
            return

        if before.channel.id != bot_channel.id:
            return

        if self._has_non_bot_members(bot_channel):
            return

        await self._schedule_empty_channel_disconnect(member.guild)

    def _should_check_empty_channel(
        self, member: discord.Member, before: discord.VoiceState
    ) -> bool:
        """Check if we should process this voice state update.

        Args:
            member: The member whose state changed.
            before: The previous voice state.

        Returns:
            True if we should check for empty channel.
        """
        # Ignore bot's own changes
        if member.id == self.bot.user.id:  # type: ignore
            return False
        # Only care about channel leaves
        return before.channel is not None

    def _get_bot_voice_channel(
        self, guild: discord.Guild
    ) -> discord.VoiceChannel | discord.StageChannel | None:
        """Get the voice channel the bot is connected to.

        Args:
            guild: The guild to check.

        Returns:
            The voice channel, or None if not connected.
        """
        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client is None or voice_client.channel is None:
            return None

        channel = voice_client.channel
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return channel
        return None

    def _has_non_bot_members(self, channel: discord.VoiceChannel | discord.StageChannel) -> bool:
        """Check if channel has any non-bot members.

        Args:
            channel: The voice channel to check.

        Returns:
            True if there are non-bot members.
        """
        return any(not m.bot for m in channel.members)

    async def _schedule_empty_channel_disconnect(self, guild: discord.Guild) -> None:
        """Schedule disconnect from empty voice channel.

        Args:
            guild: The guild to disconnect from.
        """
        logger.info("No users left in voice channel, scheduling disconnect in guild %s", guild.id)

        await asyncio.sleep(30)  # Wait for potential rejoin

        bot_channel = self._get_bot_voice_channel(guild)
        if bot_channel is None or self._has_non_bot_members(bot_channel):
            return

        await self._disconnect_and_cleanup(guild)

    async def _disconnect_and_cleanup(self, guild: discord.Guild) -> None:
        """Disconnect from voice and clean up session.

        Args:
            guild: The guild to disconnect from.
        """
        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client is None:
            return

        try:
            await voice_client.disconnect(force=False)
            logger.info("Disconnected from empty voice channel in guild %s", guild.id)

            repo = self.container.session_repository
            await repo.delete(guild.id)
        except Exception:
            logger.exception("Failed to disconnect from voice channel")

    # ─────────────────────────────────────────────────────────────────
    # Message Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Called when a message is created."""
        if self._is_bot_or_none(message.author):
            return

        if not (self._chat_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        snippet = (message.content[:80] + "…") if len(message.content) > 80 else message.content
        logger.debug("Message by %s: %s", message.author.display_name, snippet)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Called when a message is edited."""
        if self._is_bot_or_none(before.author):
            return

        if before.content == after.content:
            return

        if not (self._chat_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        logger.debug(
            "Message edit by %s: '%s' -> '%s'",
            after.author.display_name,
            before.content[:60],
            after.content[:60],
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Called when a message is deleted."""
        if self._is_bot_or_none(message.author):
            return

        if not (self._chat_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        logger.debug("Message deleted %s by %s", message.id, message.author.display_name)

    # ─────────────────────────────────────────────────────────────────
    # Reaction Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Called when a reaction is added."""
        if self._is_bot_or_none(payload.member):
            return

        if not (self._reaction_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        logger.debug(
            "Reaction add msg=%s user=%s emoji=%s",
            payload.message_id,
            getattr(payload.member, "display_name", f"user_id={payload.user_id}"),
            payload.emoji,
        )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.abc.User) -> None:
        """Called when a reaction is removed."""
        if self._is_bot_or_none(user):
            return

        if not (self._reaction_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        logger.debug(
            "Reaction remove msg=%s user=%s emoji=%s",
            reaction.message.id,
            user.display_name,
            reaction.emoji,
        )

    # ─────────────────────────────────────────────────────────────────
    # Command Error Handler
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        """Handle command errors."""
        # Handle cooldowns
        if isinstance(error, commands.CommandOnCooldown):
            retry_after = error.retry_after
            time_str = f"{retry_after:.1f}s" if retry_after >= 1 else f"{retry_after * 1000:.0f}ms"
            logger.debug(
                "Cooldown triggered for command '%s' by %s (%.2fs remaining)",
                getattr(ctx.command, "qualified_name", "<unknown>"),
                getattr(ctx.author, "id", "?"),
                retry_after,
            )
            try:
                await ctx.reply(
                    DiscordUIMessages.ERROR_COMMAND_COOLDOWN.format(time_str=time_str),
                    mention_author=False,
                )
            except discord.HTTPException:
                pass
            return

        # Handle missing permissions
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(DiscordUIMessages.ERROR_MISSING_PERMISSIONS, mention_author=False)
            return

        # Handle bot missing permissions
        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.reply(
                DiscordUIMessages.ERROR_BOT_MISSING_PERMISSIONS.format(missing=missing),
                mention_author=False,
            )
            return

        # Handle command not found (ignore silently)
        if isinstance(error, commands.CommandNotFound):
            return

        # Log other errors
        original = getattr(error, "original", error)
        logger.exception(
            "Unhandled command error in '%s'",
            getattr(ctx.command, "qualified_name", "<unknown>"),
            exc_info=original,
        )


async def setup(bot: commands.Bot) -> None:
    """Set up the event cog.

    Args:
        bot: The Discord bot instance.
    """
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(EventCog(bot, container))
