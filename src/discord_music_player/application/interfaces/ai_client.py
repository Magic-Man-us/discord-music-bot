"""
AI Client Interface

Port interface for AI-powered recommendations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.recommendations.entities import (
        Recommendation,
        RecommendationRequest,
    )


class AIClient(ABC):
    """Abstract interface for AI recommendation services.

    Implementations should handle:
    - Generating track recommendations
    - Caching to reduce API costs
    - Rate limiting
    """

    @abstractmethod
    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        """Get track recommendations based on a request.

        Args:
            request: The recommendation request with base track info.

        Returns:
            List of recommendations.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the AI service is available.

        Returns:
            True if the service can accept requests.
        """
        ...

    @abstractmethod
    def clear_cache(self) -> int:
        """Clear the recommendation cache.

        Returns:
            Number of entries cleared.
        """
        ...

    @abstractmethod
    def prune_cache(self, max_age_seconds: int) -> int:
        """Remove old cache entries.

        Args:
            max_age_seconds: Maximum age of entries to keep.

        Returns:
            Number of entries pruned.
        """
        ...

    @abstractmethod
    def get_cache_stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (hits, misses, size, etc.)
        """
        ...
