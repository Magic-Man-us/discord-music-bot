"""Per-guild tracking and editing of Discord now-playing and queued messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import UIConstants
from ....domain.shared.types import ChannelIdField, DiscordSnowflake
from ....utils.reply import truncate

from ..views.base_view import BaseInteractiveView
from .embed_builder import build_now_playing_embed, format_finished_line
from .models import GuildMessageState, TrackedMessage

_FINISHED_DELETE_AFTER = UIConstants.FINISHED_DELETE_AFTER
_QUEUED_DELETE_AFTER = UIConstants.QUEUED_DELETE_AFTER

if TYPE_CHECKING:
    from discord.ext import commands

    from ....config.container import Container
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)


class MessageStateManager:
    """Per-guild tracking of Discord messages posted for now-playing and queued tracks."""

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot
        self._state_by_guild: dict[int, GuildMessageState] = {}

    def get_state(self, guild_id: DiscordSnowflake) -> GuildMessageState:
        state = self._state_by_guild.get(guild_id)
        if state is None:
            state = GuildMessageState()
            self._state_by_guild[guild_id] = state
        return state

    # ── State mutation ─────────────────────────────────────────────

    def reserve_now_playing(self, guild_id: DiscordSnowflake) -> None:
        """Mark now-playing as pending so the auto-poster doesn't duplicate it."""
        state = self.get_state(guild_id)
        state.now_playing_reserved = True

    def track_now_playing(
        self,
        *,
        guild_id: DiscordSnowflake,
        track: Track,
        channel_id: ChannelIdField,
        message_id: DiscordSnowflake,
    ) -> None:
        state = self.get_state(guild_id)
        state.now_playing_reserved = False
        state.now_playing = TrackedMessage.for_track(
            track,
            channel_id=channel_id,
            message_id=message_id,
        )

    def track_queued(
        self,
        *,
        guild_id: DiscordSnowflake,
        track: Track,
        channel_id: ChannelIdField,
        message_id: DiscordSnowflake,
    ) -> None:
        state = self.get_state(guild_id)
        state.queued.append(
            TrackedMessage.for_track(
                track,
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    async def reset(self, guild_id: DiscordSnowflake) -> None:
        state = self._state_by_guild.pop(guild_id, None)
        if state is not None and state.now_playing is not None:
            await self._try_delete_message(state.now_playing)
        logger.debug("Cleaned up message state for guild %s", guild_id)

    async def _try_delete_message(self, tracked: TrackedMessage) -> None:
        message = await self._fetch_message(tracked)
        if message is not None:
            try:
                await message.delete()
            except discord.HTTPException:
                logger.debug("Failed to delete message %s", tracked.message_id)

    def clear_all(self) -> None:
        self._state_by_guild.clear()

    # ── Message editing ─────────────────────────────────────────────

    async def edit_message_to_one_liner(self, tracked: TrackedMessage, *, content: str) -> None:
        message = await self._fetch_message(tracked)
        if message is None:
            return

        try:
            await message.edit(content=content, embed=None, view=None)
        except discord.HTTPException:
            logger.debug(
                "Failed editing message %s in channel %s",
                tracked.message_id,
                tracked.channel_id,
            )

    async def edit_message_to_embed(
        self,
        tracked: TrackedMessage,
        *,
        embed: discord.Embed,
        view: discord.ui.View | None,
    ) -> discord.Message | None:
        message = await self._fetch_message(tracked)
        if message is None:
            return None

        try:
            await message.edit(content=None, embed=embed, view=view)
            return message
        except discord.HTTPException:
            logger.debug(
                "Failed promoting message %s in channel %s",
                tracked.message_id,
                tracked.channel_id,
            )
            return None

    async def _fetch_message(self, tracked: TrackedMessage) -> discord.Message | None:
        channel = self._bot.get_channel(tracked.channel_id)
        if channel is None:
            try:
                channel = await self._bot.fetch_channel(tracked.channel_id)
            except discord.HTTPException:
                return None

        if not isinstance(channel, discord.abc.Messageable):
            return None

        try:
            return await channel.fetch_message(tracked.message_id)
        except discord.HTTPException:
            return None

    # ── Live "Next Up" update ──────────────────────────────────────

    async def update_next_up(self, guild_id: DiscordSnowflake, next_track: Track | None) -> None:
        """Update the 'Next Up' field on the current Now Playing embed."""
        state = self._state_by_guild.get(guild_id)
        if state is None or state.now_playing is None:
            return

        message = await self._fetch_message(state.now_playing)
        if message is None:
            return

        if not message.embeds:
            return

        embed = message.embeds[0]

        next_up_value = truncate(next_track.title, 60) if next_track else UIConstants.NEXT_UP_NONE
        for i, field in enumerate(embed.fields):
            if field.name and "Next Up" in field.name:
                embed.set_field_at(i, name=field.name, value=next_up_value, inline=False)
                break

        try:
            await message.edit(embed=embed)
        except Exception:
            logger.debug("Failed to update Next Up for guild %s", guild_id)

    # ── Track-finished callback ─────────────────────────────────────

    async def on_track_finished(self, guild_id: DiscordSnowflake, track: Track) -> None:
        """Post an auto-deleting 'Finished playing' message beneath the now-playing embed."""
        state = self._state_by_guild.get(guild_id)
        if state is None:
            return

        if state.now_playing is not None:
            channel = self._bot.get_channel(state.now_playing.channel_id)
            if channel is not None and isinstance(channel, discord.abc.Messageable):
                try:
                    await channel.send(
                        format_finished_line(track),
                        delete_after=_FINISHED_DELETE_AFTER,
                    )
                except discord.HTTPException:
                    logger.debug("Failed sending finished message for guild %s", guild_id)

    async def promote_next_track(
        self,
        guild_id: DiscordSnowflake,
        next_track: Track,
        *,
        container: Container | None = None,
        upcoming_track: Track | None = None,
    ) -> None:
        """Update the now-playing embed in-place for the next track.

        Priority: reuse the existing now-playing message by editing it.
        Fallback: promote a queued message. If neither exists, do nothing
        (PlaybackCog will send a fresh now-playing embed).
        """
        state = self._state_by_guild.get(guild_id)
        if state is None:
            return

        embed = build_now_playing_embed(next_track, next_track=upcoming_track)

        if container is not None:
            from ..views.now_playing_view import NowPlayingView

            view: BaseInteractiveView = NowPlayingView(
                webpage_url=next_track.webpage_url,
                title=next_track.title,
                guild_id=guild_id,
                container=container,
            )
        else:
            from ..views.download_view import DownloadView

            view = DownloadView(webpage_url=next_track.webpage_url, title=next_track.title)

        # Try reusing the existing now-playing message first
        target = state.now_playing
        if target is not None:
            # Discard any queued message for this track since we're reusing now-playing
            state.pop_matching_queued(next_track)
            message = await self.edit_message_to_embed(target, embed=embed, view=view)
            if message is not None:
                view.set_message(message)
                # now_playing stays pointed at the same TrackedMessage
                return

        # Fallback: promote the queued message for this track
        queued_msg = state.pop_matching_queued(next_track)
        if queued_msg is not None:
            message = await self.edit_message_to_embed(queued_msg, embed=embed, view=view)
            if message is not None:
                view.set_message(message)
                state.now_playing = queued_msg
