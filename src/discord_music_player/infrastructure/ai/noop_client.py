"""No-op AI client used when AI features are disabled via settings."""

from __future__ import annotations

import logging

from discord_music_player.application.interfaces.ai_client import AIClient
from discord_music_player.domain.recommendations.entities import Recommendation, RecommendationRequest
from discord_music_player.domain.shared.types import PositiveInt
from discord_music_player.infrastructure.ai.models import AICacheStats

logger = logging.getLogger(__name__)

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
