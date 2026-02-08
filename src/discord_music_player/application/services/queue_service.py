"""Queue Application Service - manages queue operations."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ...domain.music.entities import Track
from ...domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ...domain.music.services import QueueDomainService

logger = logging.getLogger(__name__)


@dataclass
class EnqueueResult:
    """Result of an enqueue operation."""

    success: bool
    track: Track | None = None
    position: int = 0
    queue_length: int = 0
    message: str = ""
    should_start: bool = False  # True if playback should start (was idle)


@dataclass
class QueueInfo:
    """Information about the current queue."""

    current_track: Track | None
    upcoming_tracks: list[Track]
    total_length: int
    total_duration_seconds: int | None

    @property
    def tracks(self) -> list[Track]:
        """Alias for upcoming_tracks for compatibility."""
        return self.upcoming_tracks

    @property
    def total_tracks(self) -> int:
        """Alias for total_length for compatibility."""
        return self.total_length

    @property
    def total_duration(self) -> int | None:
        """Alias for total_duration_seconds for compatibility."""
        return self.total_duration_seconds


class QueueApplicationService:
    """Manages queue operations for guilds.

    This service handles adding, removing, and reordering tracks
    in a guild's playback queue.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        queue_domain_service: QueueDomainService,
    ) -> None:
        """Initialize the queue service.

        Args:
            session_repository: Repository for session persistence.
            queue_domain_service: Domain service for queue rules.
        """
        self._session_repo = session_repository
        self._queue_service = queue_domain_service

    async def enqueue(
        self,
        guild_id: int,
        track: Track,
        user_id: int,
        user_name: str,
    ) -> EnqueueResult:
        """Add a track to the end of the queue.

        Args:
            guild_id: The guild to add the track to.
            track: The track to add.
            user_id: ID of the user requesting the track.
            user_name: Name of the user requesting the track.

        Returns:
            Result of the enqueue operation.
        """
        session = await self._session_repo.get_or_create(guild_id)

        # Check if queue can accept more tracks
        if not session.can_add_to_queue:
            return EnqueueResult(
                success=False,
                message=f"Queue is full (max {session.MAX_QUEUE_SIZE} tracks)",
            )

        # Check if playback should start (nothing currently playing)
        was_idle = session.current_track is None

        # Add requester info to track
        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=datetime.now(UTC),
        )

        # Add to queue
        position = session.enqueue(track_with_requester)
        await self._session_repo.save(session)

        logger.info(LogTemplates.QUEUE_ENQUEUED, track.title, position.value, guild_id)

        if was_idle:
            message = f"Now playing: {track.title}"
        else:
            message = f"Added to queue at position {position.value + 1}"

        return EnqueueResult(
            success=True,
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
            message=message,
            should_start=was_idle,
        )

    async def enqueue_next(
        self,
        guild_id: int,
        track: Track,
        user_id: int,
        user_name: str,
    ) -> EnqueueResult:
        """Add a track to play next (front of queue).

        Args:
            guild_id: The guild to add the track to.
            track: The track to add.
            user_id: ID of the user requesting the track.
            user_name: Name of the user requesting the track.

        Returns:
            Result of the enqueue operation.
        """
        session = await self._session_repo.get_or_create(guild_id)

        if not session.can_add_to_queue:
            return EnqueueResult(
                success=False,
                message=f"Queue is full (max {session.MAX_QUEUE_SIZE} tracks)",
            )

        track_with_requester = track.with_requester(
            user_id=user_id,
            user_name=user_name,
            requested_at=datetime.now(UTC),
        )

        position = session.enqueue_next(track_with_requester)
        await self._session_repo.save(session)

        logger.info(LogTemplates.QUEUE_ENQUEUED_NEXT, track.title, guild_id)

        return EnqueueResult(
            success=True,
            track=track_with_requester,
            position=position.value,
            queue_length=session.queue_length,
            message="Added to play next",
        )

    async def remove(self, guild_id: int, position: int) -> Track | None:
        """Remove a track from the queue.

        Args:
            guild_id: The guild to remove from.
            position: Zero-based position in queue.

        Returns:
            The removed track, or None if position invalid.
        """
        session = await self._session_repo.get(guild_id)
        if session is None:
            return None

        track = session.remove_at(position)
        if track:
            await self._session_repo.save(session)
            logger.info(LogTemplates.QUEUE_REMOVED, track.title, guild_id)

        return track

    async def clear(self, guild_id: int) -> int:
        """Clear all tracks from the queue.

        Args:
            guild_id: The guild to clear.

        Returns:
            Number of tracks cleared.
        """
        session = await self._session_repo.get(guild_id)
        if session is None:
            return 0

        count = session.clear_queue()
        await self._session_repo.save(session)
        logger.info(LogTemplates.QUEUE_CLEARED, count, guild_id)
        return count

    async def shuffle(self, guild_id: int) -> bool:
        """Shuffle the queue.

        Args:
            guild_id: The guild to shuffle.

        Returns:
            True if shuffle was successful.
        """
        session = await self._session_repo.get(guild_id)
        if session is None or not session.queue:
            return False

        session.shuffle()
        await self._session_repo.save(session)
        logger.info(LogTemplates.QUEUE_SHUFFLED, guild_id)
        return True

    async def move(self, guild_id: int, from_pos: int, to_pos: int) -> bool:
        """Move a track from one position to another.

        Args:
            guild_id: The guild to modify.
            from_pos: Current position of the track.
            to_pos: Target position.

        Returns:
            True if move was successful.
        """
        session = await self._session_repo.get(guild_id)
        if session is None:
            return False

        success = session.move_track(from_pos, to_pos)
        if success:
            await self._session_repo.save(session)
            logger.info(LogTemplates.QUEUE_MOVED, from_pos, to_pos, guild_id)

        return success

    async def get_queue(self, guild_id: int) -> QueueInfo:
        """Get information about the current queue.

        Args:
            guild_id: The guild to get queue for.

        Returns:
            Queue information.
        """
        session = await self._session_repo.get(guild_id)
        if session is None:
            return QueueInfo(
                current_track=None,
                upcoming_tracks=[],
                total_length=0,
                total_duration_seconds=None,
            )

        # Calculate total duration if all tracks have durations
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

        return QueueInfo(
            current_track=session.current_track,
            upcoming_tracks=list(session.queue),
            total_length=session.queue_length + (1 if session.current_track else 0),
            total_duration_seconds=total_duration if has_all_durations else None,
        )

    async def toggle_loop(self, guild_id: int) -> str:
        """Toggle loop mode for a guild.

        Args:
            guild_id: The guild to toggle loop for.

        Returns:
            The new loop mode as a string.
        """
        session = await self._session_repo.get_or_create(guild_id)
        new_mode = session.toggle_loop()
        await self._session_repo.save(session)
        logger.info(LogTemplates.LOOP_MODE_CHANGED, new_mode.value, guild_id)
        return new_mode.value
