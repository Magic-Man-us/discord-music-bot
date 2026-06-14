"""Per-guild tracking and editing of Discord now-playing and queued messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import TimeConstants, UIConstants
from ....domain.shared.datetime_utils import utcnow
from ....domain.shared.types import ChannelIdField, DiscordSnowflake
from ....utils.logging import get_logger
from ..channel_utils import resolve_messageable
from ..views.base_view import BaseInteractiveView
from .embed_builder import build_now_playing_embed, format_finished_line
from .guild_lock_registry import GuildLockRegistry
from .models import GuildMessageState, TrackedMessage

_FINISHED_DELETE_AFTER = UIConstants.FINISHED_DELETE_AFTER
_QUEUED_DELETE_AFTER = UIConstants.QUEUED_DELETE_AFTER

if TYPE_CHECKING:
    from discord.ext import commands

    from ....config.container import Container
    from ....domain.music.entities import Track

logger = get_logger(__name__)


class MessageStateManager:
    """Per-guild tracking of Discord messages posted for now-playing and queued tracks."""

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot
        self._state_by_guild: dict[int, GuildMessageState] = {}
        # Serializes now-playing edits per guild: update_next_up and
        # promote_next_track both mutate the single now-playing message, and
        # without this a stale write could resurrect an already-advanced track.
        self._edit_locks = GuildLockRegistry()

    def get_state(self, guild_id: DiscordSnowflake) -> GuildMessageState:
        state = self._state_by_guild.get(guild_id)
        if state is None:
            state = GuildMessageState()
            self._state_by_guild[guild_id] = state
        return state

    # ── State mutation ─────────────────────────────────────────────

    def reserve_now_playing(self, guild_id: DiscordSnowflake) -> None:
        """Mark now-playing as pending so the auto-poster doesn't duplicate it.

        The reservation carries a timestamp and self-expires after
        ``NOW_PLAYING_RESERVATION_TTL_SECONDS`` so a failed/abandoned send can
        never permanently suppress auto-posting (see ``reservation_active``).
        """
        state = self.get_state(guild_id)
        state.now_playing_reserved_at = utcnow()

    def clear_now_playing_reservation(self, guild_id: DiscordSnowflake) -> None:
        """Drop a pending reservation without tracking a message (error paths)."""
        state = self._state_by_guild.get(guild_id)
        if state is not None:
            state.now_playing_reserved_at = None

    def reservation_active(self, guild_id: DiscordSnowflake) -> bool:
        """Return whether an unexpired now-playing reservation is in effect.

        Expired reservations are cleared as a side effect so the next track
        starts fresh.
        """
        state = self._state_by_guild.get(guild_id)
        if state is None or state.now_playing_reserved_at is None:
            return False
        age = (utcnow() - state.now_playing_reserved_at).total_seconds()
        if age >= TimeConstants.NOW_PLAYING_RESERVATION_TTL_SECONDS:
            state.now_playing_reserved_at = None
            return False
        return True

    def track_now_playing(
        self,
        *,
        guild_id: DiscordSnowflake,
        track: Track,
        channel_id: ChannelIdField,
        message_id: DiscordSnowflake,
    ) -> None:
        state = self.get_state(guild_id)
        state.now_playing_reserved_at = None
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
        channel = resolve_messageable(self._bot, tracked.channel_id)
        if channel is None:
            return

        try:
            partial = channel.get_partial_message(tracked.message_id)
            # delay=0 wraps the HTTP call in asyncio.create_task, avoiding
            # event-loop starvation that causes audio buffer underruns.
            await partial.delete(delay=0)
        except discord.HTTPException:
            logger.debug("Failed to delete message %s", tracked.message_id)

    def clear_all(self) -> None:
        self._state_by_guild.clear()
        self._edit_locks.clear()

    # ── Message editing ─────────────────────────────────────────────

    async def edit_message_to_one_liner(self, tracked: TrackedMessage, *, content: str) -> None:
        channel = resolve_messageable(self._bot, tracked.channel_id)
        if channel is None:
            return

        try:
            partial = channel.get_partial_message(tracked.message_id)
            await partial.edit(content=content, embed=None, view=None)
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
        """Edit a tracked message to show ``embed``/``view``.

        Returns the edited message, or ``None`` when its channel is uncached.
        Propagates ``discord.NotFound``/``discord.Forbidden`` (the message is
        gone) and other ``discord.HTTPException`` (a transient failure) so the
        caller can decide whether to repost or keep tracking the message.
        """
        channel = resolve_messageable(self._bot, tracked.channel_id)
        if channel is None:
            return None

        partial = channel.get_partial_message(tracked.message_id)
        return await partial.edit(content=None, embed=embed, view=view)

    # ── Live "Next Up" update ──────────────────────────────────────

    async def update_next_up(
        self,
        guild_id: DiscordSnowflake,
        *,
        current_track: Track | None,
        next_track: Track | None,
    ) -> None:
        """Refresh the now-playing embed's 'Next Up' field from live truth.

        Rebuilds the whole embed from the current/upcoming tracks (rather than
        patching a fetched copy) and serializes with ``promote_next_track``
        under the per-guild edit lock, so a concurrent track-advance cannot
        interleave between read and write and resurrect a stale embed.
        """
        if current_track is None:
            return
        state = self._state_by_guild.get(guild_id)
        if state is None or state.now_playing is None:
            return

        async with self._edit_locks.get(guild_id):
            tracked = state.now_playing
            if tracked is None:
                return
            # Only refresh while the tracked message still represents the track
            # we were told is current; otherwise a track-advance already moved
            # on and promote_next_track owns the embed.
            if tracked.track_key.track_id != current_track.id.value:
                return
            embed = build_now_playing_embed(current_track, next_track=next_track)
            try:
                await self._edit_now_playing_embed(tracked, embed)
            except Exception:
                logger.debug("Failed to update Next Up for guild %s", guild_id)

    async def _edit_now_playing_embed(self, tracked: TrackedMessage, embed: discord.Embed) -> None:
        """Edit a tracked message's embed in place, leaving its view intact."""
        channel = resolve_messageable(self._bot, tracked.channel_id)
        if channel is None:
            return
        partial = channel.get_partial_message(tracked.message_id)
        await partial.edit(embed=embed)

    # ── Track-finished callback ─────────────────────────────────────

    async def on_track_finished(self, guild_id: DiscordSnowflake, track: Track) -> None:
        """Post an auto-deleting 'Finished playing' message beneath the now-playing embed."""
        state = self._state_by_guild.get(guild_id)
        if state is None:
            return

        if state.now_playing is not None:
            channel = resolve_messageable(self._bot, state.now_playing.channel_id)
            if channel is not None:
                try:
                    await channel.send(
                        format_finished_line(track),
                        delete_after=_FINISHED_DELETE_AFTER,
                    )
                except discord.HTTPException:
                    logger.debug("Failed sending finished message for guild %s", guild_id)

    async def post_now_playing_if_absent(
        self,
        guild_id: DiscordSnowflake,
        *,
        track: Track,
        channel: discord.TextChannel,
        embed: discord.Embed,
        view: BaseInteractiveView,
    ) -> bool:
        """Post a fresh now-playing embed only if none is tracked, under the per-guild lock.

        Serializes against ``promote_next_track``/``update_next_up`` so concurrent
        ``TrackStartedPlaying`` handlers cannot each post a separate embed. Returns
        ``True`` if a message was posted, ``False`` if one already exists (the caller
        should update it in place instead).
        """
        async with self._edit_locks.get(guild_id):
            if self.get_state(guild_id).now_playing is not None:
                return False
            sent = await channel.send(embed=embed, view=view)
            view.set_message(sent)
            self.track_now_playing(
                guild_id=guild_id,
                track=track,
                channel_id=channel.id,
                message_id=sent.id,
            )
            return True

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

        async with self._edit_locks.get(guild_id):
            embed = build_now_playing_embed(next_track, next_track=upcoming_track)

            if container is not None:
                from ..views.now_playing_view import NowPlayingView

                view: BaseInteractiveView = NowPlayingView.for_track(
                    next_track, guild_id=guild_id, container=container
                )
            else:
                from ..views.download_view import DownloadView

                view = DownloadView(webpage_url=next_track.webpage_url, title=next_track.title)

            # Try reusing the existing now-playing message first
            target = state.now_playing
            if target is not None:
                # Discard any queued message for this track since we're reusing now-playing
                state.pop_matching_queued(next_track)
                try:
                    message = await self.edit_message_to_embed(target, embed=embed, view=view)
                except (discord.NotFound, discord.Forbidden):
                    # Message is gone — clear so we fall through to promote/repost.
                    logger.debug("Now-playing message gone for guild %s; will repost", guild_id)
                    state.now_playing = None
                except discord.HTTPException:
                    # Transient failure (rate limit / server error) — keep tracking the
                    # existing message so the next start edits it instead of posting a
                    # duplicate now-playing embed.
                    logger.debug(
                        "Transient now-playing edit failure for guild %s; keeping message",
                        guild_id,
                    )
                    return
                else:
                    if message is None:
                        # Channel uncached — keep tracking; don't post a duplicate.
                        return
                    view.set_message(message)
                    # Re-point at the now-current track so the tracked key matches
                    # what the message displays; update_next_up's consistency guard
                    # relies on this to tell a fresh update from a stale one.
                    state.now_playing = TrackedMessage.for_track(
                        next_track,
                        channel_id=target.channel_id,
                        message_id=target.message_id,
                    )
                    return

            # Fallback: promote the queued message for this track
            queued_msg = state.pop_matching_queued(next_track)
            if queued_msg is not None:
                try:
                    message = await self.edit_message_to_embed(queued_msg, embed=embed, view=view)
                except discord.HTTPException:
                    logger.debug("Failed promoting queued message for guild %s", guild_id)
                    return
                if message is not None:
                    view.set_message(message)
                    state.now_playing = queued_msg
