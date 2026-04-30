"""Live music-activity mirror for /dj follow.

A guild can follow exactly one user at a time. While following, every
distinct track that user broadcasts via Discord activity (Spotify, Apple
Music) is resolved on YouTube and enqueued. Caps at
``LimitConstants.MAX_FOLLOW_TRACKS`` then auto-disables. Auto-disables
when the followed user leaves the bot's voice channel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from ...domain.shared.constants import LimitConstants
from ...domain.shared.events import VoiceMemberLeftVoiceChannel, get_event_bus
from ...domain.shared.types import DiscordSnowflake, NonEmptyStr
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
        self._states.clear()
        self._started = False

    def enable(
        self,
        guild_id: DiscordSnowflake,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> None:
        self._states[guild_id] = FollowState(user_id=user_id, user_name=user_name)
        logger.info("FollowMode enabled in guild %s for user %s", guild_id, user_id)

    def disable(self, guild_id: DiscordSnowflake) -> None:
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

        Returns ``True`` if a new track was enqueued, ``False`` for any
        no-op (not followed, dedup hit, resolution failure). The dedup key
        is the resolved query string itself — stable for the same
        artist/title across noisy presence pings.
        """
        state = self._states.get(guild_id)
        if state is None or state.user_id != user_id:
            return False

        if query == state.last_key:
            return False

        state.last_key = query

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
            logger.debug(
                "FollowMode enqueue rejected in guild %s: %s", guild_id, result.message
            )
            return False

        state.enqueued_count += 1
        logger.info(
            "FollowMode enqueued '%s' (%d/%d) in guild %s",
            track.title,
            state.enqueued_count,
            LimitConstants.MAX_FOLLOW_TRACKS,
            guild_id,
        )

        if result.should_start:
            await self._playback_service.start_playback(guild_id)

        if state.enqueued_count >= LimitConstants.MAX_FOLLOW_TRACKS:
            self.disable(guild_id)

        return True

    async def _on_member_left(self, event: VoiceMemberLeftVoiceChannel) -> None:
        state = self._states.get(event.guild_id)
        if state is not None and state.user_id == event.user_id:
            self.disable(event.guild_id)
