"""Abstract base classes defining the contracts for recommendation caching."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from discord_music_player.domain.recommendations.entities import RecommendationSet


class RecommendationCacheRepository(ABC):
    """Cache for recommendation sets to limit expensive AI API calls."""

    @abstractmethod
    async def get(self, cache_key: str) -> RecommendationSet | None:
        """Retrieve a cached recommendation set, or None if missing/expired."""
        ...

    @abstractmethod
    async def save(self, recommendation_set: RecommendationSet) -> None:
        """Cache a recommendation set."""
        ...

    @abstractmethod
    async def delete(self, cache_key: str) -> bool:
        """Delete a cached recommendation set."""
        ...

    @abstractmethod
    async def clear(self) -> int:
        """Clear all cached recommendations."""
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove all expired cache entries.

        Critical for preventing memory leaks in long-running bot instances.
        """
        ...

    @abstractmethod
    async def prune(self, max_entries: int) -> int:
        """Prune cache to max_entries, removing oldest first."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Get the number of cached entries."""
        ...

    @abstractmethod
    async def get_stats(self) -> dict[str, int | datetime | None]:
        """Get cache statistics."""
        ...
