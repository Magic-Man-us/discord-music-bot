"""Queue Application Service - manages queue operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.music.entities import Track
from ...domain.music.enums import LoopMode
from ...domain.shared.datetime_utils import utcnow
from ...domain.shared.exceptions import BusinessRuleViolationError
from ...domain.shared.types import DiscordSnowflake, NonEmptyStr, QueuePositionInt
from .queue_models import BatchEnqueueResult, EnqueueMeta, EnqueueResult, QueueSnapshot

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository

logger = logging.getLogger(__name__)


class QueueApplicationService:

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
    ) -> None:
        self._session_repo = session_repository

    async def enqueue(
        self,
        guild_id: DiscordSnowflake,
        track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> EnqueueResult:
        session = await self._session_repo.get_or_create(guild_id)
        was_idle = session.current_track is None

        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=utcnow(),
        )

        try:
            position = session.enqueue(track_with_requester)
        except BusinessRuleViolationError as exc:
            return EnqueueResult.failure(exc.message)

        await self._session_repo.save(session)
        logger.info("Enqueued track '%s' at position %s in guild %s", track.title, position.value, guild_id)

        message = f"Now playing: {track.title}" if was_idle else f"Added to queue at position {position.value + 1}"
        meta = EnqueueMeta(
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
            should_start=was_idle,
        )
        return EnqueueResult.ok(meta=meta, message=message)

    async def enqueue_next(
        self,
        guild_id: DiscordSnowflake,
        track: Track,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> EnqueueResult:
        session = await self._session_repo.get_or_create(guild_id)

        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=utcnow(),
        )

        try:
            position = session.enqueue_next(track_with_requester)
        except BusinessRuleViolationError as exc:
            return EnqueueResult.failure(exc.message)

        await self._session_repo.save(session)
        logger.info("Enqueued track '%s' to play next in guild %s", track.title, guild_id)

        meta = EnqueueMeta(
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
        )
        return EnqueueResult.ok(meta=meta, message="Added to play next")

    async def enqueue_batch(
        self,
        guild_id: DiscordSnowflake,
        tracks: list[Track],
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> BatchEnqueueResult:
        """Enqueue multiple tracks, returning how many succeeded and whether playback should start."""
        count = 0
        should_start = False
        for track in tracks:
            result = await self.enqueue(
                guild_id=guild_id,
                track=track,
                user_id=user_id,
                user_name=user_name,
            )
            if result.success:
                count += 1
                if result.should_start:
                    should_start = True
        return BatchEnqueueResult(enqueued=count, should_start=should_start)

    async def remove(self, guild_id: DiscordSnowflake, position: QueuePositionInt) -> Track | None:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return None

        track = session.remove_at(position)
        if track:
            await self._session_repo.save(session)
            logger.info("Removed track '%s' from queue in guild %s", track.title, guild_id)

        return track

    async def clear(self, guild_id: DiscordSnowflake) -> int:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        count = session.clear_queue()
        await self._session_repo.save(session)
        logger.info("Cleared %s tracks from queue in guild %s", count, guild_id)
        return count

    async def clear_recommendations(self, guild_id: DiscordSnowflake) -> int:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        count = session.clear_recommendations()
        await self._session_repo.save(session)
        logger.info("Cleared %d AI recommendations from queue in guild %s", count, guild_id)
        return count

    async def shuffle(self, guild_id: DiscordSnowflake) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None or not session.queue:
            return False

        session.shuffle()
        await self._session_repo.save(session)
        logger.info("Shuffled queue in guild %s", guild_id)
        return True

    async def move(self, guild_id: DiscordSnowflake, from_pos: QueuePositionInt, to_pos: QueuePositionInt) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return False

        success = session.move_track(from_pos, to_pos)
        if success:
            await self._session_repo.save(session)
            logger.info("Moved track from %s to %s in guild %s", from_pos, to_pos, guild_id)

        return success

    async def get_queue(self, guild_id: DiscordSnowflake) -> QueueSnapshot:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return QueueSnapshot(
                current_track=None,
                tracks=[],
                total_tracks=0,
                total_duration=None,
            )

        total_duration = 0
        has_all_durations = True

        if session.current_track and session.current_track.duration_seconds:
            total_duration += session.current_track.duration_seconds
        elif session.current_track:
            has_all_durations = False

        for track in session.queue:
            if track.duration_seconds:
                total_duration += track.duration_seconds
            else:
                has_all_durations = False

        return QueueSnapshot(
            current_track=session.current_track,
            tracks=list(session.queue),
            total_tracks=session.queue_length + (1 if session.current_track else 0),
            total_duration=total_duration if has_all_durations else None,
        )

    async def toggle_loop(self, guild_id: DiscordSnowflake) -> LoopMode:
        session = await self._session_repo.get_or_create(guild_id)
        new_mode = session.toggle_loop()
        await self._session_repo.save(session)
        logger.info("Loop mode changed to %s in guild %s", new_mode.value, guild_id)
        return new_mode
