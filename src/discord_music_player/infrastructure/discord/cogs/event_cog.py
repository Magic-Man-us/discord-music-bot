"""Discord event listeners for lifecycle, voice, guild, and message events."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from discord_music_player.domain.shared.constants import ConfigKeys
from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class EventCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container
        self._resumed_logged_once = False

        # Idle disconnect timers per guild
        self._idle_timers: dict[int, asyncio.Task[None]] = {}

        from ....domain.shared.events import get_event_bus

        self._event_bus = get_event_bus()

        self._chat_logging = self._env_flag(ConfigKeys.LOG_EVENT_MESSAGES)
        self._reaction_logging = self._env_flag(ConfigKeys.LOG_EVENT_REACTIONS)

        # Subscribe to events for idle disconnect
        from ....domain.shared.events import QueueExhausted, TrackStartedPlaying

        self._event_bus.subscribe(QueueExhausted, self._on_queue_exhausted)
        self._event_bus.subscribe(TrackStartedPlaying, self._on_track_started)

    @staticmethod
    def _env_flag(name: str) -> bool:
        return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_bot_or_none(user: discord.abc.User | discord.Member | None) -> bool:
        return user is None or bool(getattr(user, "bot", False))

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info("Bot ready as %s (%s)", self.bot.user, getattr(self.bot.user, "id", "?"))

    @commands.Cog.listener()
    async def on_connect(self) -> None:
        logger.info("WebSocket connected")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        logger.warning("WebSocket disconnected")

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        if not self._resumed_logged_once:
            logger.info("WebSocket session resumed")
            self._resumed_logged_once = True

    # ─────────────────────────────────────────────────────────────────
    # Guild Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        logger.info("Joined guild: %s (%s)", guild.name, guild.id)
        if guild.system_channel:
            try:
                await guild.system_channel.send(DiscordUIMessages.SUCCESS_GUILD_WELCOME)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        logger.info("Left guild: %s (%s)", guild.name, guild.id)

        try:
            self.container.message_state_manager.reset(guild.id)
        except Exception:
            logger.debug("Could not cleanup message state for guild %s", guild.id)

        try:
            repo = self.container.session_repository
            await repo.delete(guild.id)
            logger.debug("Cleaned up session for guild %s", guild.id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.name != after.name:
            logger.info("Guild renamed: %s -> %s", before.name, after.name)

    # ─────────────────────────────────────────────────────────────────
    # Member Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        logger.info("Member joined: %s (%s) guild=%s", member, member.id, member.guild.id)
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
        logger.info(
            "Member left: %s (%s) guild=%s", member.display_name, member.id, member.guild.id
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        logger.warning("User banned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        logger.info("User unbanned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    # ─────────────────────────────────────────────────────────────────
    # Idle Disconnect (AFK timeout)
    # ─────────────────────────────────────────────────────────────────

    async def _on_queue_exhausted(self, event: Any) -> None:
        """Start an idle timer when the queue runs out."""
        guild_id: int = event.guild_id
        self._cancel_idle_timer(guild_id)

        from ....domain.shared.constants import TimeConstants

        timeout = TimeConstants.IDLE_DISCONNECT_SECONDS
        logger.info(
            "Queue exhausted in guild %s, scheduling idle disconnect in %ss",
            guild_id,
            timeout,
        )
        self._idle_timers[guild_id] = asyncio.create_task(
            self._idle_disconnect(guild_id, timeout)
        )

    async def _on_track_started(self, event: Any) -> None:
        """Cancel any pending idle timer when a new track starts."""
        self._cancel_idle_timer(event.guild_id)

    def _cancel_idle_timer(self, guild_id: int) -> None:
        timer = self._idle_timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()
            logger.debug("Cancelled idle timer for guild %s", guild_id)

    async def _idle_disconnect(self, guild_id: int, timeout: int) -> None:
        """Wait *timeout* seconds, then disconnect if still idle."""
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        # Verify still idle — no current track playing
        session = await self.container.session_repository.get(guild_id)
        if session is not None and session.is_playing:
            return

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return

        logger.info("Idle timeout reached, disconnecting from guild %s", guild_id)
        await self._disconnect_and_cleanup(guild)

    # ─────────────────────────────────────────────────────────────────
    # Voice Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.bot:
            return

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
        if member.id == self.bot.user.id:  # type: ignore
            return False
        return before.channel is not None

    def _get_bot_voice_channel(
        self, guild: discord.Guild
    ) -> discord.VoiceChannel | discord.StageChannel | None:
        voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
        if voice_client is None or voice_client.channel is None:
            return None

        channel = voice_client.channel
        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return channel
        return None

    def _has_non_bot_members(self, channel: discord.VoiceChannel | discord.StageChannel) -> bool:
        return any(not m.bot for m in channel.members)

    async def _schedule_empty_channel_disconnect(self, guild: discord.Guild) -> None:
        logger.info("No users left in voice channel, scheduling disconnect in guild %s", guild.id)
        await asyncio.sleep(30)

        bot_channel = self._get_bot_voice_channel(guild)
        if bot_channel is None or self._has_non_bot_members(bot_channel):
            return

        await self._disconnect_and_cleanup(guild)

    async def _disconnect_and_cleanup(self, guild: discord.Guild) -> None:
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
        if self._is_bot_or_none(message.author):
            return

        if not (self._chat_logging and logger.isEnabledFor(logging.DEBUG)):
            return

        snippet = (message.content[:80] + "…") if len(message.content) > 80 else message.content
        logger.debug("Message by %s: %s", message.author.display_name, snippet)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
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

        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(DiscordUIMessages.ERROR_MISSING_PERMISSIONS, mention_author=False)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.reply(
                DiscordUIMessages.ERROR_BOT_MISSING_PERMISSIONS.format(missing=missing),
                mention_author=False,
            )
            return

        if isinstance(error, commands.CommandNotFound):
            return

        original = getattr(error, "original", error)
        logger.exception(
            "Unhandled command error in '%s'",
            getattr(ctx.command, "qualified_name", "<unknown>"),
            exc_info=original,
        )


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(EventCog(bot, container))
