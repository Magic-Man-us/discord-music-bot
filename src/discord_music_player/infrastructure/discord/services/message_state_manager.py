"""Tracks and manages Discord messages for now-playing and queued track announcements."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from pydantic import BaseModel, ConfigDict, Field

from discord_music_player.domain.shared.types import DiscordSnowflake, NonEmptyStr, UtcDatetimeField
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from discord.ext import commands

    from ....config.container import Container
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)


class TrackKey(BaseModel):
    model_config = ConfigDict(frozen=True)

    track_id: NonEmptyStr
    requested_by_id: DiscordSnowflake | None = None
    requested_at: UtcDatetimeField | None = None

    @classmethod
    def from_track(cls, track: Track) -> TrackKey:
        return cls(
            track_id=track.id.value,
            requested_by_id=track.requested_by_id,
            requested_at=track.requested_at,
        )


class TrackedMessage(BaseModel):
    channel_id: DiscordSnowflake
    message_id: DiscordSnowflake
    track_key: TrackKey

    @classmethod
    def from_track(cls, track: Track, *, channel_id: int, message_id: int) -> TrackedMessage:
        return cls(
            channel_id=channel_id,
            message_id=message_id,
            track_key=TrackKey.from_track(track),
        )


class GuildMessageState(BaseModel):
    now_playing: TrackedMessage | None = None
    queued: deque[TrackedMessage] = Field(default_factory=deque)

    def pop_matching_queued(self, track: Track) -> TrackedMessage | None:
        target = TrackKey.from_track(track)
        if not self.queued:
            return None

        found: TrackedMessage | None = None
        for tracked in self.queued:
            if tracked.track_key == target:
                found = tracked
                break

        if found is None:
            return None

        self.queued = deque(t for t in self.queued if t.track_key != target)
        return found


class MessageStateManager:
    """Per-guild tracking of Discord messages posted for now-playing and queued tracks."""

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot
        self._state_by_guild: dict[int, GuildMessageState] = {}

    def get_state(self, guild_id: int) -> GuildMessageState:
        state = self._state_by_guild.get(guild_id)
        if state is None:
            state = GuildMessageState()
            self._state_by_guild[guild_id] = state
        return state

    def track_now_playing(
        self,
        *,
        guild_id: int,
        track: Track,
        channel_id: int,
        message_id: int,
    ) -> None:
        state = self.get_state(guild_id)
        state.now_playing = TrackedMessage.from_track(
            track,
            channel_id=channel_id,
            message_id=message_id,
        )

    def track_queued(
        self,
        *,
        guild_id: int,
        track: Track,
        channel_id: int,
        message_id: int,
    ) -> None:
        state = self.get_state(guild_id)
        state.queued.append(
            TrackedMessage.from_track(
                track,
                channel_id=channel_id,
                message_id=message_id,
            )
        )

    def reset(self, guild_id: int) -> None:
        self._state_by_guild.pop(guild_id, None)
        logger.debug("Cleaned up message state for guild %s", guild_id)

    def clear_all(self) -> None:
        self._state_by_guild.clear()

    # ── Formatting helpers ──────────────────────────────────────────

    @staticmethod
    def format_requester(track: Track) -> str:
        if track.requested_by_id:
            return f"<@{track.requested_by_id}>"
        if track.requested_by_name:
            return track.requested_by_name
        return "Unknown"

    @staticmethod
    def format_queued_line(track: Track) -> str:
        requester = MessageStateManager.format_requester(track)
        title = truncate(track.title, 80)
        return f"\u23ed\ufe0f Queued for play: [{title}]({track.webpage_url}) \u2014 {requester}"

    @staticmethod
    def format_finished_line(track: Track) -> str:
        requester = MessageStateManager.format_requester(track)
        title = truncate(track.title, 80)
        return f"\u2705 Finished playing: [{title}]({track.webpage_url}) \u2014 {requester}"

    @staticmethod
    def build_now_playing_embed(
        track: Track, *, next_track: Track | None = None
    ) -> discord.Embed:
        from ....domain.shared.messages import DiscordUIMessages

        requester_display = MessageStateManager.format_requester(track)
        artist_or_uploader = track.artist or track.uploader
        likes_display = f"{track.like_count:,}" if track.like_count is not None else None

        description_lines = [f"[{track.title}]({track.webpage_url})"]
        description_lines.append(f"Requested by: {requester_display}")

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_NOW_PLAYING,
            description="\n".join(description_lines),
            color=discord.Color.green(),
        )

        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)

        embed.add_field(
            name="\u23f1\ufe0f Duration",
            value=format_duration(track.duration_seconds),
            inline=True,
        )

        if artist_or_uploader:
            embed.add_field(
                name="\U0001f464 Artist",
                value=truncate(artist_or_uploader, 64),
                inline=True,
            )

        if likes_display:
            embed.add_field(
                name="\U0001f44d Likes",
                value=likes_display,
                inline=True,
            )

        if next_track:
            embed.add_field(
                name="\u23ed\ufe0f Next Up",
                value=truncate(next_track.title, 60),
                inline=False,
            )
        else:
            embed.add_field(
                name="\u23ed\ufe0f Next Up",
                value=DiscordUIMessages.UP_NEXT_NONE,
                inline=False,
            )

        return embed

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

        fetch_message = getattr(channel, "fetch_message", None)
        if fetch_message is None:
            return None

        try:
            return await fetch_message(tracked.message_id)
        except discord.HTTPException:
            return None

    # ── Track-finished callback ─────────────────────────────────────

    async def on_track_finished(self, guild_id: int, track: Track) -> None:
        """Update Discord messages when a track finishes: collapse now-playing, promote next."""
        state = self._state_by_guild.get(guild_id)
        if state is None:
            return

        if state.now_playing is not None:
            await self.edit_message_to_one_liner(
                state.now_playing,
                content=self.format_finished_line(track),
            )
            state.now_playing = None

    async def promote_next_track(
        self,
        guild_id: int,
        next_track: Track,
        *,
        container: Container | None = None,
        upcoming_track: Track | None = None,
    ) -> None:
        """Promote the queued message for the next track to a now-playing embed."""
        state = self._state_by_guild.get(guild_id)
        if state is None:
            return

        queued_msg = state.pop_matching_queued(next_track)
        if queued_msg is None:
            return

        embed = self.build_now_playing_embed(next_track, next_track=upcoming_track)

        if container is not None:
            from ..views.now_playing_view import NowPlayingView

            view: discord.ui.View = NowPlayingView(
                webpage_url=next_track.webpage_url,
                title=next_track.title,
                guild_id=guild_id,
                container=container,
            )
        else:
            from ..views.download_view import DownloadView

            view = DownloadView(webpage_url=next_track.webpage_url, title=next_track.title)

        message = await self.edit_message_to_embed(queued_msg, embed=embed, view=view)
        if message is not None:
            if hasattr(view, "set_message"):
                view.set_message(message)
            state.now_playing = queued_msg
