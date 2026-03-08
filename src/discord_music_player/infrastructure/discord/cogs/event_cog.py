"""Discord event listeners for lifecycle, voice, guild, and message events."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import commands

from discord_music_player.domain.shared.constants import ConfigKeys, DiscordEmbedLimits, UIConstants
from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.utils.reply import truncate

if TYPE_CHECKING:
    from ....config.container import Container

class EventCog(BaseCog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        super().__init__(bot, container)
        self._resumed_logged_once = False

        # Idle disconnect timers per guild
        self._idle_timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}
        # Empty-channel disconnect timers per guild
        self._empty_channel_timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}

        from ....domain.shared.events import get_event_bus

        self._event_bus = get_event_bus()

        self._chat_logging = self._env_flag(ConfigKeys.LOG_EVENT_MESSAGES)
        self._reaction_logging = self._env_flag(ConfigKeys.LOG_EVENT_REACTIONS)

        # Subscribe to events for idle disconnect
        from ....domain.shared.events import QueueExhausted, TrackStartedPlaying

        self._event_bus.subscribe(QueueExhausted, self._on_queue_exhausted)
        self._event_bus.subscribe(TrackStartedPlaying, self._on_track_started)

    @staticmethod
    def _env_flag(key: str) -> bool:  # ConfigKeys constant
        return os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _is_bot_or_none(user: discord.abc.User | discord.Member | None) -> bool:
        return user is None or user.bot

    # ─────────────────────────────────────────────────────────────────
    # Lifecycle Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        bot_user = self.bot.user
        self.logger.info("Bot ready as %s (%s)", bot_user, bot_user.id if bot_user else "?")

    @commands.Cog.listener()
    async def on_connect(self) -> None:
        self.logger.info("WebSocket connected")

    @commands.Cog.listener()
    async def on_disconnect(self) -> None:
        self.logger.warning("WebSocket disconnected")

    @commands.Cog.listener()
    async def on_resumed(self) -> None:
        if not self._resumed_logged_once:
            self.logger.info("WebSocket session resumed")
            self._resumed_logged_once = True

    # ─────────────────────────────────────────────────────────────────
    # Guild Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        self.logger.info("Joined guild: %s (%s)", guild.name, guild.id)
        if guild.system_channel:
            try:
                await guild.system_channel.send("Thanks for inviting me! Use `/help` for commands.")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self.logger.info("Left guild: %s (%s)", guild.name, guild.id)

        self._cancel_idle_timer(guild.id)
        self._cancel_empty_channel_timer(guild.id)

        try:
            self.container.message_state_manager.reset(guild.id)
        except Exception:
            self.logger.debug("Could not cleanup message state for guild %s", guild.id)

        try:
            repo = self.container.session_repository
            await repo.delete(guild.id)
            self.logger.debug("Cleaned up session for guild %s", guild.id)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.name != after.name:
            self.logger.info("Guild renamed: %s -> %s", before.name, after.name)

    # ─────────────────────────────────────────────────────────────────
    # Member Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        self.logger.info("Member joined: %s (%s) guild=%s", member, member.id, member.guild.id)
        ch = member.guild.system_channel
        if ch:
            try:
                await ch.send(
                    f"Welcome {member.mention}!"
                )
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        self.logger.info(
            "Member left: %s (%s) guild=%s", member.display_name, member.id, member.guild.id
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        self.logger.warning("User banned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        self.logger.info("User unbanned: %s (%s) guild=%s", user.display_name, user.id, guild.id)

    # ─────────────────────────────────────────────────────────────────
    # Idle Disconnect (AFK timeout)
    # ─────────────────────────────────────────────────────────────────

    async def _on_queue_exhausted(self, event: Any) -> None:
        """Start an idle timer when the queue runs out."""
        guild_id: DiscordSnowflake = event.guild_id
        self._cancel_idle_timer(guild_id)

        from ....domain.shared.constants import TimeConstants

        timeout = TimeConstants.IDLE_DISCONNECT_SECONDS
        self.logger.info(
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

    def _cancel_idle_timer(self, guild_id: DiscordSnowflake) -> None:
        timer = self._idle_timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()
            self.logger.debug("Cancelled idle timer for guild %s", guild_id)

    async def _idle_disconnect(self, guild_id: DiscordSnowflake, timeout: int) -> None:
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

        self.logger.info("Idle timeout reached, disconnecting from guild %s", guild_id)
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

        old_ch = before.channel
        new_ch = after.channel
        joined = new_ch is not None and (old_ch is None or old_ch.id != new_ch.id)
        left = old_ch is not None and (new_ch is None or new_ch.id != old_ch.id)

        if joined:
            await self._handle_member_joined(member, new_ch)  # type: ignore[arg-type]

        if left:
            await self._handle_member_left(member, old_ch)  # type: ignore[arg-type]

    async def _handle_member_joined(
        self,
        member: discord.Member,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Track warmup, cancel empty-channel timer, and publish join event."""
        guild = member.guild
        self.container.voice_warmup_tracker.mark_joined(
            guild_id=guild.id,
            user_id=member.id,
        )

        bot_channel = self._get_bot_voice_channel(guild)
        if bot_channel is not None and channel.id == bot_channel.id:
            self._cancel_empty_channel_timer(guild.id)

        from ....domain.shared.events import VoiceMemberJoinedVoiceChannel

        await self._event_bus.publish(
            VoiceMemberJoinedVoiceChannel(
                guild_id=guild.id,
                channel_id=channel.id,
                user_id=member.id,
            )
        )

    async def _handle_member_left(
        self,
        member: discord.Member,
        channel: discord.abc.GuildChannel,
    ) -> None:
        """Publish leave event and check for empty-channel disconnect."""
        guild = member.guild
        bot_channel = self._get_bot_voice_channel(guild)

        if bot_channel is not None and channel.id == bot_channel.id:
            from ....domain.shared.events import VoiceMemberLeftVoiceChannel

            await self._event_bus.publish(
                VoiceMemberLeftVoiceChannel(
                    guild_id=guild.id,
                    channel_id=channel.id,
                    user_id=member.id,
                )
            )

            if not self._is_self(member) and not self._has_non_bot_members(bot_channel):
                await self._schedule_empty_channel_disconnect(guild)

    def _is_self(self, member: discord.Member) -> bool:
        return member.id == self.bot.user.id  # type: ignore[union-attr]

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
        """Fire-and-forget: schedule a delayed disconnect if the channel stays empty."""
        self._cancel_empty_channel_timer(guild.id)

        from ....domain.shared.constants import TimeConstants

        timeout = TimeConstants.EMPTY_CHANNEL_DISCONNECT_SECONDS
        self.logger.info(
            "No users left in voice channel, scheduling disconnect in %ss for guild %s",
            timeout,
            guild.id,
        )
        self._empty_channel_timers[guild.id] = asyncio.create_task(
            self._empty_channel_disconnect(guild, timeout)
        )

    def _cancel_empty_channel_timer(self, guild_id: DiscordSnowflake) -> None:
        timer = self._empty_channel_timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()
            self.logger.debug("Cancelled empty-channel timer for guild %s", guild_id)

    async def _empty_channel_disconnect(self, guild: discord.Guild, timeout: int) -> None:
        """Wait *timeout* seconds, then disconnect if the channel is still empty."""
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        bot_channel = self._get_bot_voice_channel(guild)
        if bot_channel is None or self._has_non_bot_members(bot_channel):
            return

        self.logger.info("Empty-channel timeout reached, disconnecting guild %s", guild.id)
        await self._disconnect_and_cleanup(guild)

    async def _disconnect_and_cleanup(self, guild: discord.Guild) -> None:
        try:
            await self.container.playback_service.cleanup_guild(guild.id)
            self.container.message_state_manager.reset(guild.id)
        except Exception:
            self.logger.exception("Failed to disconnect and cleanup guild %s", guild.id)

    # ─────────────────────────────────────────────────────────────────
    # Message Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if self._is_bot_or_none(message.author):
            return

        if not (self._chat_logging and self.logger.isEnabledFor(logging.DEBUG)):
            return

        snippet = truncate(message.content, DiscordEmbedLimits.MESSAGE_CONTENT_SNIPPET)
        self.logger.debug("Message by %s: %s", message.author.display_name, snippet)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if self._is_bot_or_none(before.author):
            return

        if before.content == after.content:
            return

        if not (self._chat_logging and self.logger.isEnabledFor(logging.DEBUG)):
            return

        self.logger.debug(
            "Message edit by %s: '%s' -> '%s'",
            after.author.display_name,
            before.content[:60],
            after.content[:60],
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if self._is_bot_or_none(message.author):
            return

        if not (self._chat_logging and self.logger.isEnabledFor(logging.DEBUG)):
            return

        self.logger.debug("Message deleted %s by %s", message.id, message.author.display_name)

    # ─────────────────────────────────────────────────────────────────
    # Reaction Events
    # ─────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        if self._is_bot_or_none(payload.member):
            return

        if not (self._reaction_logging and self.logger.isEnabledFor(logging.DEBUG)):
            return

        self.logger.debug(
            "Reaction add msg=%s user=%s emoji=%s",
            payload.message_id,
            payload.member.display_name if payload.member else f"user_id={payload.user_id}",
            payload.emoji,
        )

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.abc.User) -> None:
        if self._is_bot_or_none(user):
            return

        if not (self._reaction_logging and self.logger.isEnabledFor(logging.DEBUG)):
            return

        self.logger.debug(
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
            time_str = f"{retry_after:.1f}s" if retry_after >= 1 else f"{retry_after * UIConstants.MS_PER_SECOND:.0f}ms"
            self.logger.debug(
                "Cooldown triggered for command '%s' by %s (%.2fs remaining)",
                ctx.command.qualified_name if ctx.command else "<unknown>",
                ctx.author.id,
                retry_after,
            )
            try:
                await ctx.reply(
                    f"Command on cooldown. Try again in {time_str}.",
                    mention_author=False,
                )
            except discord.HTTPException:
                pass
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You don't have permission to use this command.", mention_author=False)
            return

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.reply(
                f"I need these permissions: {missing}",
                mention_author=False,
            )
            return

        if isinstance(error, commands.CommandNotFound):
            return

        original = error.original if isinstance(error, commands.CommandInvokeError) else error
        self.logger.exception(
            "Unhandled command error in '%s'",
            ctx.command.qualified_name if ctx.command else "<unknown>",
            exc_info=original,
        )


setup = EventCog.setup
