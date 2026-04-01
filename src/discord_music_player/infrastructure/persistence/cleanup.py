"""Periodic cleanup of stale sessions, history, cache, and vote data."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from datetime import timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, computed_field

from ...domain.shared.datetime_utils import utcnow
from ...domain.shared.types import NonNegativeInt

if TYPE_CHECKING:
    from ...config.settings import CleanupSettings
    from ...domain.music.repository import SessionRepository, TrackHistoryRepository
    from ...domain.recommendations.repository import RecommendationCacheRepository
    from ...domain.voting.repository import VoteSessionRepository

logger = logging.getLogger(__name__)


class CleanupJob:
    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        history_repository: TrackHistoryRepository,
        cache_repository: RecommendationCacheRepository,
        vote_repository: VoteSessionRepository,
        settings: CleanupSettings,
    ) -> None:
        self._session_repo = session_repository
        self._history_repo = history_repository
        self._cache_repo = cache_repository
        self._vote_repo = vote_repository
        self._settings = settings
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._running:
            logger.warning("Cleanup job is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Cleanup job started")

    async def stop(self) -> None:
        self._running = False

        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("Cleanup job stopped")

    async def _run_loop(self) -> None:
        interval_seconds = self._settings.cleanup_interval_minutes * 60

        while self._running:
            try:
                await self.run_cleanup()
            except Exception:
                logger.exception("Error during cleanup")

            try:
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break

    async def _run_one(
        self, label: str, stats: CleanupStats, field: str, coro: Awaitable[int]
    ) -> None:
        """Execute a single cleanup operation, logging failures without propagating."""
        try:
            setattr(stats, field, await coro)
        except Exception as e:
            logger.error("Failed to cleanup %s: %r", label, e)

    async def run_cleanup(self) -> CleanupStats:
        logger.debug("Running cleanup cycle")

        stale_cutoff = utcnow() - timedelta(hours=self._settings.stale_session_hours)
        history_cutoff = utcnow() - timedelta(days=self._settings.history_retention_days)

        stats = CleanupStats()
        await self._run_one(
            "sessions", stats, "sessions_cleaned", self._session_repo.cleanup_stale(stale_cutoff)
        )
        await self._run_one(
            "history", stats, "history_cleaned", self._history_repo.cleanup_old(history_cutoff)
        )
        await self._run_one("cache", stats, "cache_cleaned", self._cache_repo.cleanup_expired())
        await self._run_one(
            "vote sessions", stats, "votes_cleaned", self._vote_repo.cleanup_expired()
        )

        if stats.total_cleaned > 0:
            logger.info(
                "Cleanup completed: %s sessions, %s history entries, %s cache entries, %s vote sessions",
                stats.sessions_cleaned,
                stats.history_cleaned,
                stats.cache_cleaned,
                stats.votes_cleaned,
            )

        return stats

    @property
    def is_running(self) -> bool:
        return self._running


class CleanupStats(BaseModel):
    """Accumulator for cleanup operation results."""

    model_config = ConfigDict(validate_assignment=True)

    sessions_cleaned: NonNegativeInt = 0
    history_cleaned: NonNegativeInt = 0
    cache_cleaned: NonNegativeInt = 0
    votes_cleaned: NonNegativeInt = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_cleaned(self) -> int:
        return (
            self.sessions_cleaned + self.history_cleaned + self.cache_cleaned + self.votes_cleaned
        )
