"""No-op AI client used when AI features are disabled via settings."""

from __future__ import annotations

from ...application.interfaces.ai_client import AIClient
from ...domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
)
from ...domain.shared.types import PositiveInt
from ...utils.logging import get_logger
from .models import AICacheStats

logger = get_logger(__name__)

_ZERO_STATS = AICacheStats(size=0, hits=0, misses=0, inflight=0)


class NoOpAIClient(AIClient):
    """AI client that does nothing. Returns empty results for all operations.

    Used when ``AISettings.enabled`` is ``False`` so consumers don't need
    conditional logic — they just get empty/unavailable responses.
    """

    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        return []

    async def is_available(self) -> bool:
        return False

    def clear_cache(self) -> int:
        return 0

    def prune_cache(self, max_age_seconds: PositiveInt) -> int:
        return 0

    def get_cache_stats(self) -> AICacheStats:
        return _ZERO_STATS
