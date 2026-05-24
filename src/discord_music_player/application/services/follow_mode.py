"""Live music-activity mirror for /playmine.

A guild can follow exactly one user at a time. While following, every
distinct track that user broadcasts via Discord activity (Spotify, Apple
Music) is resolved on YouTube and played *immediately* — the bot mirrors
the followed user in real time, dropping whatever was queued so a local
"next" press is reflected straight away. Caps at the per-follow
``max_tracks`` then auto-disables. Auto-disables when the followed user
leaves the bot's voice channel, and disconnects after a grace period once
their listening activity disappears.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...domain.shared.constants import LimitConstants, TimeConstants
from ...domain.shared.events import (
    FollowModeStopped,
    VoiceMemberLeftVoiceChannel,
    get_event_bus,
)
from ...domain.shared.types import (
    DiscordSnowflake,
    FollowTrackCount,
    NonEmptyStr,
)
from ...utils.logging import get_logger

if TYPE_CHECKING:
    from ..interfaces.audio_resolver import AudioResolver
    from .playback_service import PlaybackApplicationService
    from .queue_service import QueueApplicationService

logger = get_logger(__name__)


class FollowState(BaseModel):
    """Per-guild follow state. Mutable across track changes."""

    model_config = ConfigDict(strict=True)

    user_id: DiscordSnowflake
    user_name: NonEmptyStr
    max_tracks: FollowTrackCount = LimitConstants.MAX_FOLLOW_TRACKS
    last_key: str | None = None
    enqueued_count: int = 0


class FollowMode:
    def __init__(
        self,
        *,
        audio_resolver: AudioResolver,
        queue_service: QueueApplicationService,
        playback_service: PlaybackApplicationService,
    ) -> None:
        self._audio_resolver = audio_resolver
        self._queue_service = queue_service
        self._playback_service = playback_service
        self._bus = get_event_bus()
        self._started = False
        self._states: dict[DiscordSnowflake, FollowState] = {}
        self._idle_timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._started = True
        logger.info("FollowMode started")

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        for timer in self._idle_timers.values():
            if not timer.done():
                timer.cancel()
        self._idle_timers.clear()
        self._states.clear()
        self._started = False

    def enable(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        *,
        max_tracks: FollowTrackCount = LimitConstants.MAX_FOLLOW_TRACKS,
        last_key: str | None = None,
        enqueued_count: int = 0,
    ) -> None:
        self._cancel_idle_timer(guild_id)
        self._states[guild_id] = FollowState(
            user_id=user_id,
            user_name=user_name,
            max_tracks=max_tracks,
            last_key=last_key,
            enqueued_count=enqueued_count,
        )
        logger.info(
            "FollowMode enabled in guild %s for user %s (max %d tracks)",
            guild_id,
            user_id,
            max_tracks,
        )

    def disable(self, guild_id: DiscordSnowflake) -> None:
        self._cancel_idle_timer(guild_id)
        if self._states.pop(guild_id, None) is not None:
            logger.info("FollowMode disabled in guild %s", guild_id)

    def is_enabled(self, guild_id: DiscordSnowflake) -> bool:
        return guild_id in self._states

    def followed_user_id(self, guild_id: DiscordSnowflake) -> DiscordSnowflake | None:
        state = self._states.get(guild_id)
        return state.user_id if state is not None else None

    async def on_track_change(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        query: NonEmptyStr,
    ) -> bool:
        """Process a presence change for the followed user.

        Mirrors in real time: a new track replaces the queue and plays
        immediately (so a local "next" press is reflected). Returns ``True``
        if a new track was played, ``False`` for any no-op (not followed,
        dedup hit, resolution failure). The dedup key is the resolved query
        string itself — stable for the same artist/title across noisy
        presence pings.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return False

        # The user is actively listening — cancel any pending stop-disconnect.
        self._cancel_idle_timer(guild_id)

        if query == state.last_key:
            return False

        state.last_key = query

        track = await self._audio_resolver.resolve(query)
        if track is None:
            logger.debug(
                "FollowMode resolve failed for query=%r in guild %s", query, guild_id
            )
            return False

        # True mirror: drop the existing backlog and make this the live track.
        await self._queue_service.clear(guild_id)
        result = await self._queue_service.enqueue(
            guild_id=guild_id,
            track=track.model_copy(update={"is_direct_request": True}),
            user_id=state.user_id,
            user_name=state.user_name,
        )
        if not result.success:
            logger.debug(
                "FollowMode enqueue rejected in guild %s: %s", guild_id, result.message
            )
            return False

        state.enqueued_count += 1
        logger.info(
            "FollowMode mirrored '%s' (%d/%d) in guild %s",
            track.title,
            state.enqueued_count,
            state.max_tracks,
            guild_id,
        )

        if result.should_start:
            await self._playback_service.start_playback(guild_id)
        else:
            await self._playback_service.cut_to_next_track(guild_id)

        if state.enqueued_count >= state.max_tracks:
            self.disable(guild_id)

        return True

    async def on_activity_cleared(
        self, guild_id: DiscordSnowflake, user_id: DiscordSnowflake
    ) -> None:
        """The followed user's music activity vanished — start a grace timer.

        If they don't resume within ``FOLLOW_STOP_GRACE_SECONDS`` the bot
        disconnects. A timer already counting down is left untouched so
        repeated "no music" presence pings don't keep extending it.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return

        existing = self._idle_timers.get(guild_id)
        if existing is not None and not existing.done():
            return

        logger.info(
            "Followed user idle in guild %s; disconnecting in %ss unless they resume",
            guild_id,
            TimeConstants.FOLLOW_STOP_GRACE_SECONDS,
        )
        self._idle_timers[guild_id] = asyncio.create_task(
            self._grace_then_disconnect(guild_id)
        )

    def _cancel_idle_timer(self, guild_id: DiscordSnowflake) -> None:
        timer = self._idle_timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()

    async def _grace_then_disconnect(self, guild_id: DiscordSnowflake) -> None:
        try:
            await asyncio.sleep(TimeConstants.FOLLOW_STOP_GRACE_SECONDS)
        except asyncio.CancelledError:
            return

        # Own our slot before mutating state so disable() can't cancel us.
        self._idle_timers.pop(guild_id, None)
        if self._states.pop(guild_id, None) is None:
            return

        logger.info("Followed user stopped in guild %s; disconnecting", guild_id)
        await self._bus.publish(FollowModeStopped(guild_id=guild_id))

    async def _on_member_left(self, event: VoiceMemberLeftVoiceChannel) -> None:
        state = self._states.get(event.guild_id)
        if state is not None and state.user_id == event.user_id:
            self.disable(event.guild_id)
