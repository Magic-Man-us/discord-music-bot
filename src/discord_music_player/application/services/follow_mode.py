"""Live music-activity mirror for /playmine.

A guild follows exactly one user at a time. The song they are listening to
when they invoke /playmine plays immediately — and because they may be deep
into that track, the bot lags behind, which is the *buffer* this mode relies
on. Every subsequent track they broadcast is appended to the queue behind a
dwell gate: it is only queued once it has stayed their current song for
``FOLLOW_DWELL_SECONDS``, so songs they skip past quickly never reach the
queue. The mirror runs until ``max_tracks`` songs have *played through* —
a skipped mirror track frees its slot rather than counting — then
auto-disables; it also disconnects after a grace period once their
listening activity disappears.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from ...domain.shared.constants import LimitConstants, TimeConstants
from ...domain.shared.events import (
    FollowModeStopped,
    TrackFinishedPlaying,
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
    from ...domain.music.entities import Track
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
    last_enqueued_key: str | None = None
    pending_key: str | None = None
    # Mirror tracks that played through (the limit counts these); a skip never
    # increments it, so skipping frees a slot for one more mirror.
    kept_count: int = 0
    # Track IDs queued by the mirror but not yet played/skipped. The enqueue
    # budget is kept_count + len(pending_track_ids), capped at max_tracks.
    pending_track_ids: set[str] = Field(default_factory=set)
    # Dedup against every key mirrored this session, so a revisited song
    # (A → B → A) isn't queued twice — not just the single most recent one.
    enqueued_keys: set[str] = Field(default_factory=set)


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
        self._dwell_timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}
        self._idle_timers: dict[DiscordSnowflake, asyncio.Task[None]] = {}
        self._on_next_track_queued: Callable[[DiscordSnowflake, Track], Awaitable[None]] | None = (
            None
        )

    def set_next_track_queued_callback(
        self, callback: Callable[[DiscordSnowflake, Track], Awaitable[None]] | None
    ) -> None:
        """Set a callback fired when follow mode fills an empty upcoming slot."""
        self._on_next_track_queued = callback

    def start(self) -> None:
        if self._started:
            return
        self._bus.subscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._bus.subscribe(TrackFinishedPlaying, self._on_track_finished)
        self._started = True
        logger.info("FollowMode started")

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(VoiceMemberLeftVoiceChannel, self._on_member_left)
        self._bus.unsubscribe(TrackFinishedPlaying, self._on_track_finished)
        for guild_id in list(self._states):
            self._cancel_dwell_timer(guild_id)
            self._cancel_idle_timer(guild_id)
        self._states.clear()
        self._started = False

    def enable(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        *,
        max_tracks: FollowTrackCount = LimitConstants.MAX_FOLLOW_TRACKS,
        last_enqueued_key: str | None = None,
        kept_count: int = 0,
    ) -> None:
        self._cancel_dwell_timer(guild_id)
        self._cancel_idle_timer(guild_id)
        state = FollowState(
            user_id=user_id,
            user_name=user_name,
            max_tracks=max_tracks,
            last_enqueued_key=last_enqueued_key,
            kept_count=kept_count,
        )
        if last_enqueued_key:
            state.enqueued_keys.add(last_enqueued_key)
        self._states[guild_id] = state
        logger.info(
            "FollowMode enabled in guild %s for user %s (max %d tracks)",
            guild_id,
            user_id,
            max_tracks,
        )

    def disable(self, guild_id: DiscordSnowflake) -> None:
        self._cancel_dwell_timer(guild_id)
        self._cancel_idle_timer(guild_id)
        if self._states.pop(guild_id, None) is not None:
            logger.info("FollowMode disabled in guild %s", guild_id)

    def is_enabled(self, guild_id: DiscordSnowflake) -> bool:
        return guild_id in self._states

    def followed_user_id(self, guild_id: DiscordSnowflake) -> DiscordSnowflake | None:
        state = self._states.get(guild_id)
        return state.user_id if state is not None else None

    async def seed_current(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        query: NonEmptyStr,
    ) -> bool:
        """Play the song the user is on right now, immediately and ungated.

        This is the deliberate /playmine starting point, so it bypasses the
        dwell gate. Returns ``True`` if it was queued/started.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return False
        if query in state.enqueued_keys:
            return False
        return await self._enqueue(state, guild_id, query)

    async def on_track_change(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        query: NonEmptyStr,
    ) -> bool:
        """Arm the dwell gate for a presence change from the followed user.

        Nothing is queued here. A new distinct song (re)starts the dwell
        timer; only if it survives ``FOLLOW_DWELL_SECONDS`` does it get
        appended (see ``_dwell_then_enqueue``). Returns ``True`` when a fresh
        dwell timer was armed.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return False

        # The user is actively listening — cancel any pending stop-disconnect.
        self._cancel_idle_timer(guild_id)

        if query == state.pending_key or query in state.enqueued_keys:
            return False

        # A different song than what's queued/pending — restart the gate so a
        # quick skip past the previous candidate drops it.
        self._cancel_dwell_timer(guild_id)
        state.pending_key = query
        self._dwell_timers[guild_id] = asyncio.create_task(
            self._dwell_then_enqueue(guild_id, query)
        )
        return True

    async def on_activity_cleared(
        self, guild_id: DiscordSnowflake, user_id: DiscordSnowflake
    ) -> None:
        """The followed user's music activity vanished — start a grace timer.

        Also abandons any song still in its dwell window (they stopped before
        it qualified). If they don't resume within ``FOLLOW_STOP_GRACE_SECONDS``
        the bot disconnects.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return

        self._cancel_dwell_timer(guild_id)
        state.pending_key = None

        existing = self._idle_timers.get(guild_id)
        if existing is not None and not existing.done():
            return

        logger.info(
            "Followed user idle in guild %s; disconnecting in %ss unless they resume",
            guild_id,
            TimeConstants.FOLLOW_STOP_GRACE_SECONDS,
        )
        self._idle_timers[guild_id] = asyncio.create_task(self._grace_then_disconnect(guild_id))

    async def _dwell_then_enqueue(self, guild_id: DiscordSnowflake, query: NonEmptyStr) -> None:
        try:
            await asyncio.sleep(TimeConstants.FOLLOW_DWELL_SECONDS)
        except asyncio.CancelledError:
            return

        self._dwell_timers.pop(guild_id, None)
        state = self._states.get(guild_id)
        if state is None or state.pending_key != query:
            return  # disabled or superseded by a newer song

        state.pending_key = None
        await self._enqueue(state, guild_id, query)

    async def _enqueue(
        self, state: FollowState, guild_id: DiscordSnowflake, query: NonEmptyStr
    ) -> bool:
        """Resolve and append the track; start playback only if idle (buffer)."""
        # Budget = tracks already kept + tracks still in flight. Skips drop out
        # of pending without counting, which is what frees a slot.
        if state.kept_count + len(state.pending_track_ids) >= state.max_tracks:
            return False

        track = await self._audio_resolver.resolve(query)
        if track is None:
            logger.debug("FollowMode resolve failed for query=%r in guild %s", query, guild_id)
            return False

        result = await self._queue_service.enqueue(
            guild_id=guild_id,
            track=track.model_copy(update={"is_direct_request": True}),
            user_id=state.user_id,
            user_name=state.user_name,
        )
        if not result.success:
            logger.debug("FollowMode enqueue rejected in guild %s: %s", guild_id, result.message)
            return False

        state.last_enqueued_key = query
        state.enqueued_keys.add(query)
        state.pending_track_ids.add(track.id.value)
        logger.info(
            "FollowMode queued '%s' (%d kept + %d in flight / %d) in guild %s",
            track.title,
            state.kept_count,
            len(state.pending_track_ids),
            state.max_tracks,
            guild_id,
        )

        # Only start when nothing is playing; otherwise it rides the buffer and
        # plays when the current track finishes (continuous, no skip).
        if result.should_start:
            await self._playback_service.start_playback(guild_id)
        elif result.position == 0 and result.track is not None:
            await self._notify_next_track_queued(guild_id, result.track)

        return True

    async def _notify_next_track_queued(self, guild_id: DiscordSnowflake, track: Track) -> None:
        """Notify infrastructure that the visible upcoming track changed."""
        if self._on_next_track_queued is None:
            return

        try:
            await self._on_next_track_queued(guild_id, track)
        except Exception:
            logger.debug("FollowMode next-track callback failed in guild %s", guild_id)

    async def _on_track_finished(self, event: TrackFinishedPlaying) -> None:
        """Settle a mirror track's slot once it finishes or is skipped.

        A completed track counts toward ``max_tracks`` and auto-stops the
        mirror at the cap; a skipped one is released without counting, so its
        slot is freed for one more mirror.
        """
        state = self._states.get(event.guild_id)
        if state is None:
            return
        track_id = event.track_id.value
        if track_id not in state.pending_track_ids:
            return

        state.pending_track_ids.discard(track_id)
        if event.was_skipped:
            logger.debug("FollowMode mirror track skipped in guild %s; slot freed", event.guild_id)
            return

        state.kept_count += 1
        logger.info(
            "FollowMode kept %d/%d in guild %s",
            state.kept_count,
            state.max_tracks,
            event.guild_id,
        )
        if state.kept_count >= state.max_tracks:
            self.disable(event.guild_id)

    def _cancel_dwell_timer(self, guild_id: DiscordSnowflake) -> None:
        timer = self._dwell_timers.pop(guild_id, None)
        if timer is not None and not timer.done():
            timer.cancel()

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
        self._cancel_dwell_timer(guild_id)
        if self._states.pop(guild_id, None) is None:
            return

        logger.info("Followed user stopped in guild %s; disconnecting", guild_id)
        await self._bus.publish(FollowModeStopped(guild_id=guild_id))

    async def _on_member_left(self, event: VoiceMemberLeftVoiceChannel) -> None:
        state = self._states.get(event.guild_id)
        if state is not None and state.user_id == event.user_id:
            self.disable(event.guild_id)
