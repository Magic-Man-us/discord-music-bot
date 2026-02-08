"""
Recommendations Domain Repository Interfaces

Abstract base classes defining the contracts for recommendation caching.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from discord_music_player.domain.recommendations.entities import RecommendationSet


class RecommendationCacheRepository(ABC):
    """Abstract repository for caching recommendation sets.

    Recommendations can be expensive to generate (AI API calls),
    so caching is important for performance and cost control.
    """

    @abstractmethod
    async def get(self, cache_key: str) -> RecommendationSet | None:
        """Retrieve a cached recommendation set.

        Args:
            cache_key: The cache key for the recommendations.

        Returns:
            The cached recommendation set if found and not expired,
            None otherwise.
        """
        ...

    @abstractmethod
    async def save(self, recommendation_set: RecommendationSet) -> None:
        """Cache a recommendation set.

        Args:
            recommendation_set: The recommendation set to cache.
        """
        ...

    @abstractmethod
    async def delete(self, cache_key: str) -> bool:
        """Delete a cached recommendation set.

        Args:
            cache_key: The cache key to delete.

        Returns:
            True if the entry was deleted.
        """
        ...

    @abstractmethod
    async def clear(self) -> int:
        """Clear all cached recommendations.

        Returns:
            Number of entries cleared.
        """
        ...

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove all expired cache entries.

        This is critical for preventing memory leaks in long-running
        bot instances.

        Returns:
            Number of entries cleaned up.
        """
        ...

    @abstractmethod
    async def prune(self, max_entries: int) -> int:
        """Prune cache to a maximum number of entries.

        Removes oldest entries first. This provides a hard cap on
        memory usage.

        Args:
            max_entries: Maximum number of entries to keep.

        Returns:
            Number of entries pruned.
        """
        ...

    @abstractmethod
    async def count(self) -> int:
        """Get the number of cached entries.

        Returns:
            Total cache entry count.
        """
        ...

    @abstractmethod
    async def get_stats(self) -> dict[str, int | datetime | None]:
        """Get cache statistics.

        Returns:
            Dictionary with stats like count, oldest entry, etc.
        """
        ...
