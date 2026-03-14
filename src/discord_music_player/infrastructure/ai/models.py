"""Pydantic models for AI recommendation client data transformation.

These are infrastructure-specific models for parsing AI API responses
and caching recommendation results.
"""

from __future__ import annotations

import time
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, computed_field

from discord_music_player.domain.recommendations.entities import Recommendation
from discord_music_player.domain.shared.types import (
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeFloat,
    NonNegativeInt,
    PercentageInt,
    PositiveInt,
)

AI_TIMEOUT: Final[float] = 20.0


class AIRecommendationItem(BaseModel):
    """A single recommendation item from the AI response."""

    model_config = ConfigDict(frozen=True)

    title: NonEmptyStr
    artist: NonEmptyStr | None = None
    query: str = ""
    url: HttpUrlStr | None = None

    def to_domain(self) -> Recommendation:
        query = self.query or f"{self.artist or ''} {self.title}".strip()
        return Recommendation(
            title=self.title,
            artist=self.artist,
            query=query,
            url=self.url,
        )


class AIRecommendationResponse(BaseModel):
    """Structured output returned by the AI agent."""

    model_config = ConfigDict(frozen=True)

    recs: list[AIRecommendationItem] = Field(default_factory=list)

    def to_domain_list(self) -> list[Recommendation]:
        return [item.to_domain() for item in self.recs]


class AICacheEntry(BaseModel):
    """Cached AI recommendation response."""

    model_config = ConfigDict(frozen=True)

    data: list[AIRecommendationItem]
    created_at: NonNegativeFloat = Field(default_factory=time.time)

    def is_expired(self, ttl_seconds: PositiveInt) -> bool:
        return (time.time() - self.created_at) > ttl_seconds


class AIUsageStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_input_tokens: NonNegativeInt = 0
    total_output_tokens: NonNegativeInt = 0
    total_requests: NonNegativeInt = 0
    total_calls: NonNegativeInt = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_tokens(self) -> NonNegativeInt:
        return self.total_input_tokens + self.total_output_tokens


class AICacheStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    size: NonNegativeInt
    hits: NonNegativeInt
    misses: NonNegativeInt
    inflight: NonNegativeInt
    usage: AIUsageStats = Field(default_factory=AIUsageStats)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def hit_rate(self) -> PercentageInt:
        total = self.hits + self.misses
        if total == 0:
            return 0
        return int((self.hits / total) * 100)
