"""AI recommendation client with caching and singleflight, powered by pydantic-ai."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from discord_music_player.application.interfaces.ai_client import AIClient
from discord_music_player.config.settings import AISettings
from discord_music_player.domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
)
from discord_music_player.domain.shared.messages import LogTemplates


class AIRecommendationItem(BaseModel):
    title: str = Field(..., min_length=1)
    artist: str | None = None
    query: str = ""
    url: str | None = None

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

    recs: list[AIRecommendationItem] = Field(default_factory=list)

    def to_domain_list(self) -> list[Recommendation]:
        return [item.to_domain() for item in self.recs]


logger = logging.getLogger(__name__)

AI_TIMEOUT: float = 20.0

SYSTEM_PROMPT = """You are an expert music recommender specializing in finding highly similar tracks.

Your goal: Recommend songs that share MULTIPLE characteristics with the base track:
- Same or very similar genre
- Similar tempo and energy level
- Similar vocal style (if applicable)
- Same era or time period
- Similar production style
- Matching mood/emotion

Rules:
- Return EXACTLY the requested number of recommendations
- Each recommendation should feel like it belongs on the same playlist
- Prioritize deep similarity over variety
- NEVER recommend the base track itself (even under a different name/version)
- Mix up the artists - avoid recommending multiple songs by the same artist
- Prefer specific, unambiguous search queries that will resolve on YouTube
- Set url to null if uncertain

Format each recommendation with:
- title: Song title (without artist)
- artist: Artist name
- query: Full search string optimized for YouTube (e.g., "Artist Name - Song Title")
"""


class CacheEntry(BaseModel):
    data: list[dict[str, Any]]
    created_at: float = Field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.created_at) > ttl_seconds


class AIRecommendationClient(AIClient):
    def __init__(self, settings: AISettings | None = None) -> None:
        self._settings = settings or AISettings()
        self._agent: Agent[None, AIRecommendationResponse] | None = None

        self._cache: dict[str, CacheEntry] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._inflight: dict[str, asyncio.Future[list[dict[str, Any]]]] = {}

    def _get_agent(self) -> Agent[None, AIRecommendationResponse]:
        if self._agent is not None:
            return self._agent

        self._agent = Agent(
            self._settings.model,
            output_type=AIRecommendationResponse,
            system_prompt=SYSTEM_PROMPT,
        )
        logger.info(LogTemplates.AI_CLIENT_INITIALIZED, self._settings.model, AI_TIMEOUT)
        return self._agent

    def _cache_key(self, request: RecommendationRequest) -> str:
        title = request.base_track_title.strip().lower()
        artist = (request.base_track_artist or "").strip().lower()
        return f"{title}|{artist}|{request.count}|{self._settings.model}"

    async def _call_api(self, user_prompt: str) -> AIRecommendationResponse:
        agent = self._get_agent()

        try:
            result = await agent.run(
                user_prompt,
                model_settings={
                    "max_tokens": self._settings.max_tokens,
                    "temperature": self._settings.temperature,
                    "timeout": AI_TIMEOUT,
                },
            )
            return result.output
        except Exception as e:
            self._handle_api_error(e)
            raise

    def _handle_api_error(self, error: Exception) -> None:
        logger.warning(
            LogTemplates.AI_API_ERROR_RETRY,
            1,
            1,
            error.__class__.__name__,
        )

    async def _fetch_recommendations_raw(
        self, request: RecommendationRequest
    ) -> list[dict[str, Any]]:
        cache_key = self._cache_key(request)

        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired(self._settings.cache_ttl_seconds):
                self._cache_hits += 1
                logger.debug(LogTemplates.CACHE_HIT, request.base_track_title)
                return entry.data
            else:
                del self._cache[cache_key]

        self._cache_misses += 1

        # Singleflight: deduplicate concurrent identical requests
        if cache_key in self._inflight:
            logger.debug(LogTemplates.CACHE_JOIN_INFLIGHT, request.base_track_title)
            return await self._inflight[cache_key]

        future: asyncio.Future[list[dict[str, Any]]] = asyncio.Future()
        self._inflight[cache_key] = future

        try:
            user_prompt = (
                f"Count: {request.count}\n"
                f"Base title: {request.base_track_title}\n"
                f"Base artist: {request.base_track_artist or ''}\n"
            )

            logger.debug(
                LogTemplates.AI_FETCHING_RECOMMENDATIONS, request.base_track_title, request.count
            )

            response = await self._call_api(user_prompt)

            recs = [item.model_dump() for item in response.recs]

            self._cache[cache_key] = CacheEntry(data=recs)
            future.set_result(recs)

            logger.debug(
                LogTemplates.AI_GENERATED_RECOMMENDATIONS, len(recs), request.base_track_title
            )

            return recs

        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            self._inflight.pop(cache_key, None)

    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        try:
            raw_recs = await self._fetch_recommendations_raw(request)
            response = AIRecommendationResponse.model_validate({"recs": raw_recs})
            recommendations = response.to_domain_list()

            return recommendations[: request.count]

        except Exception as e:
            logger.error(LogTemplates.AI_REQUEST_FAILED, e)
            return []

    async def is_available(self) -> bool:
        try:
            self._get_agent()
            return True
        except Exception:
            return False

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info(LogTemplates.CACHE_CLEARED, count)
        return count

    def prune_cache(self, max_age_seconds: int) -> int:
        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items() if (now - entry.created_at) > max_age_seconds
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(LogTemplates.CACHE_EXPIRED_PRUNED, len(expired_keys))

        return len(expired_keys)

    def get_cache_stats(self) -> dict[str, int]:
        return {
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": int(
                (self._cache_hits / max(1, self._cache_hits + self._cache_misses)) * 100
            ),
            "inflight": len(self._inflight),
        }
