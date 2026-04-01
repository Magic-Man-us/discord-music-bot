"""AI recommendation client with caching and singleflight, powered by pydantic-ai."""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from ...application.interfaces.ai_client import AIClient
from ...config.settings import AISettings
from ...domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
)
from ...domain.shared.types import NonEmptyStr, PositiveInt
from .models import (
    AI_TIMEOUT,
    AICacheEntry,
    AICacheStats,
    AIRecommendationItem,
    AIRecommendationResponse,
    AIUsageStats,
)

SYSTEM_PROMPT: Final[
    str
] = """You are an expert music recommender specializing in finding highly similar tracks.

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


class AIRecommendationClient(AIClient):
    def __init__(self, settings: AISettings | None = None) -> None:
        self._settings = settings or AISettings()
        self._agent: Agent[None, AIRecommendationResponse] | None = None
        self._logger = logging.getLogger(type(self).__module__)

        self._cache: dict[NonEmptyStr, AICacheEntry] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._inflight: dict[NonEmptyStr, asyncio.Future[list[AIRecommendationItem]]] = {}

        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_requests: int = 0
        self._total_calls: int = 0

    def _get_agent(self) -> Agent[None, AIRecommendationResponse]:
        if self._agent is not None:
            return self._agent

        self._agent = Agent(
            self._settings.model,
            output_type=AIRecommendationResponse,
            system_prompt=SYSTEM_PROMPT,
        )
        self._logger.info(
            "AI client initialized (model=%s, timeout=%ss)", self._settings.model, AI_TIMEOUT
        )
        return self._agent

    def _cache_key(self, request: RecommendationRequest) -> NonEmptyStr:
        title = request.base_track_title.strip().lower()
        artist = (request.base_track_artist or "").strip().lower()
        excludes = ",".join(sorted(request.exclude_tracks))
        context = ",".join(f"{(s.artist or '')}:{s.title}" for s in request.session_context)
        return f"{title}|{artist}|{request.count}|{excludes}|{context}"

    @staticmethod
    def _sanitize(text: str) -> str:
        return text.replace("`", "'")

    def _build_prompt(self, request: RecommendationRequest) -> str:
        parts = [
            f"Count: {request.count}",
            f"Base title: ```{self._sanitize(request.base_track_title)}```",
            f"Base artist: ```{self._sanitize(request.base_track_artist or '')}```",
        ]

        if request.exclude_tracks:
            lines = "\n".join(f"- {self._sanitize(t)}" for t in request.exclude_tracks)
            parts.append(f"\nDo NOT recommend any of these tracks (already played):\n{lines}")

        if request.session_context:
            lines = "\n".join(
                f"- ```{self._sanitize(s.artist or '')} - {self._sanitize(s.title)}```"
                for s in request.session_context
            )
            parts.append(f"\nRecent session tracks (match this overall mood/vibe):\n{lines}")

        return "\n".join(parts)

    async def _call_api(self, user_prompt: str) -> AIRecommendationResponse:
        agent = self._get_agent()

        try:
            settings = ModelSettings(
                max_tokens=self._settings.max_tokens,
                temperature=self._settings.temperature,
                timeout=AI_TIMEOUT,
            )
            result = await agent.run(user_prompt, model_settings=settings)

            usage = result.usage()
            self._total_input_tokens += usage.input_tokens
            self._total_output_tokens += usage.output_tokens
            self._total_requests += usage.requests
            self._total_calls += 1

            return result.output
        except Exception as e:
            self._handle_api_error(e)
            raise

    def _handle_api_error(self, error: Exception) -> None:
        self._logger.warning("AI API error: %s", error.__class__.__name__)

    async def _fetch_recommendations_raw(
        self, request: RecommendationRequest
    ) -> list[AIRecommendationItem]:
        cache_key = self._cache_key(request)

        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired(self._settings.cache_ttl_seconds):
                self._cache_hits += 1
                self._logger.debug("Cache hit for '%s'", request.base_track_title)
                return entry.data
            else:
                del self._cache[cache_key]

        self._cache_misses += 1

        # Singleflight: deduplicate concurrent identical requests
        if cache_key in self._inflight:
            self._logger.debug("Joining in-flight request for '%s'", request.base_track_title)
            return await self._inflight[cache_key]

        future: asyncio.Future[list[AIRecommendationItem]] = asyncio.Future()
        self._inflight[cache_key] = future

        try:
            user_prompt = self._build_prompt(request)

            self._logger.debug(
                "Fetching recommendations for '%s' (count=%d)",
                request.base_track_title,
                request.count,
            )

            response = await self._call_api(user_prompt)

            self._cache[cache_key] = AICacheEntry(data=response.recs)
            future.set_result(response.recs)

            self._logger.debug(
                "Generated %d recommendations for '%s'",
                len(response.recs),
                request.base_track_title,
            )

            return response.recs

        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            self._inflight.pop(cache_key, None)

    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        try:
            items = await self._fetch_recommendations_raw(request)
            response = AIRecommendationResponse(recs=items)
            recommendations = response.to_domain_list()

            return recommendations[: request.count]

        except Exception as e:
            self._logger.error("Failed to get recommendations: %s", e)
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
        self._logger.info("Cleared %d cache entries", count)
        return count

    def prune_cache(self, max_age_seconds: PositiveInt) -> int:
        expired_keys = [
            key for key, entry in self._cache.items() if entry.is_expired(max_age_seconds)
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            self._logger.info("Pruned %d expired cache entries", len(expired_keys))

        return len(expired_keys)

    def get_cache_stats(self) -> AICacheStats:
        usage = AIUsageStats(
            total_input_tokens=self._total_input_tokens,
            total_output_tokens=self._total_output_tokens,
            total_requests=self._total_requests,
            total_calls=self._total_calls,
        )
        return AICacheStats(
            size=len(self._cache),
            hits=self._cache_hits,
            misses=self._cache_misses,
            inflight=len(self._inflight),
            usage=usage,
        )
