"""Port interface for AI-powered recommendations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from discord_music_player.domain.shared.types import PositiveInt

if TYPE_CHECKING:
    from ...domain.recommendations.entities import (
        Recommendation,
        RecommendationRequest,
    )
    from ...infrastructure.ai.models import AICacheStats


class AIClient(ABC):
    """Interface for AI-powered track recommendation services."""

    @abstractmethod
    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        """Get track recommendations based on a request."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...

    @abstractmethod
    def clear_cache(self) -> int:
        """Clear the recommendation cache and return the number of entries cleared."""
        ...

    @abstractmethod
    def prune_cache(self, max_age_seconds: PositiveInt) -> int:
        """Remove cache entries older than max_age_seconds."""
        ...

    @abstractmethod
    def get_cache_stats(self) -> AICacheStats:
        """Get cache statistics."""
        ...
