"""Session cleanup job for preventing memory leaks.

This module provides a background task that periodically cleans up:
- Stale guild playback sessions (guilds the bot left)
- Old track history entries
- Expired recommendation cache entries
- Expired/old vote sessions

"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...config.settings import CleanupSettings
    from ...domain.music.repository import SessionRepository, TrackHistoryRepository
    from ...domain.recommendations.repository import RecommendationCacheRepository
    from ...domain.voting.repository import VoteSessionRepository

logger = logging.getLogger(__name__)


class CleanupJob:
    """Background job for cleaning up stale resources.

    This job runs periodically to remove:
    - Stale sessions from guilds the bot has left
    - Old history entries
    - Expired cache entries
    - Old vote sessions
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        history_repository: TrackHistoryRepository,
        cache_repository: RecommendationCacheRepository,
        vote_repository: VoteSessionRepository,
        settings: CleanupSettings,
    ) -> None:
        """Initialize the cleanup job.

        Args:
            session_repository: Repository for session cleanup.
            history_repository: Repository for history cleanup.
            cache_repository: Repository for cache cleanup.
            vote_repository: Repository for vote session cleanup.
            settings: Cleanup configuration settings.
        """
        self._session_repo = session_repository
        self._history_repo = history_repository
        self._cache_repo = cache_repository
        self._vote_repo = vote_repository
        self._settings = settings
        self._running = False
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the cleanup job as a background task."""
        if self._running:
            logger.warning(LogTemplates.CLEANUP_ALREADY_RUNNING)
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(LogTemplates.CLEANUP_STARTED)

    async def stop(self) -> None:
        """Stop the cleanup job."""
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info(LogTemplates.CLEANUP_STOPPED)

    async def _run_loop(self) -> None:
        """Main loop that runs cleanup at regular intervals."""
        interval_seconds = self._settings.cleanup_interval_minutes * 60

        while self._running:
            try:
                await self.run_cleanup()
            except Exception:
                logger.exception("Error during cleanup")

            # Wait for next interval
            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break

    async def run_cleanup(self) -> CleanupStats:
        """Run a single cleanup cycle.

        Returns:
            Statistics about what was cleaned up.
        """
        stats = CleanupStats()

        logger.debug(LogTemplates.CLEANUP_CYCLE_RUNNING)

        # Clean up stale sessions
        stale_cutoff = datetime.now(tz=UTC) - timedelta(hours=self._settings.stale_session_hours)
        try:
            stats.sessions_cleaned = await self._session_repo.cleanup_stale(stale_cutoff)
        except Exception as e:
            logger.error(LogTemplates.CLEANUP_SESSIONS_FAILED, e)

        # Clean up old history (keep 30 days)
        history_cutoff = datetime.now(tz=UTC) - timedelta(days=30)
        try:
            stats.history_cleaned = await self._history_repo.cleanup_old(history_cutoff)
        except Exception as e:
            logger.error(LogTemplates.CLEANUP_HISTORY_FAILED, e)

        # Clean up expired cache
        try:
            stats.cache_cleaned = await self._cache_repo.cleanup_expired()
        except Exception as e:
            logger.error(LogTemplates.CLEANUP_CACHE_FAILED, e)

        # Clean up expired vote sessions
        try:
            stats.votes_cleaned = await self._vote_repo.cleanup_expired()
        except Exception as e:
            logger.error(LogTemplates.CLEANUP_VOTE_SESSIONS_FAILED, e)

        if stats.total_cleaned > 0:
            logger.info(
                LogTemplates.CLEANUP_COMPLETED,
                stats.sessions_cleaned,
                stats.history_cleaned,
                stats.cache_cleaned,
                stats.votes_cleaned,
            )

        return stats

    @property
    def is_running(self) -> bool:
        """Check if the cleanup job is running."""
        return self._running


class CleanupStats:
    """Statistics from a cleanup run."""

    def __init__(self) -> None:
        self.sessions_cleaned: int = 0
        self.history_cleaned: int = 0
        self.cache_cleaned: int = 0
        self.votes_cleaned: int = 0

    @property
    def total_cleaned(self) -> int:
        """Get total number of entries cleaned."""
        return (
            self.sessions_cleaned + self.history_cleaned + self.cache_cleaned + self.votes_cleaned
        )

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "sessions": self.sessions_cleaned,
            "history": self.history_cleaned,
            "cache": self.cache_cleaned,
            "votes": self.votes_cleaned,
            "total": self.total_cleaned,
        }
