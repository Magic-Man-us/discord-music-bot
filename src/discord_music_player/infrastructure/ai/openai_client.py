"""
OpenAI Recommendation Client

Infrastructure implementation of AIClient using OpenAI API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, Field

from discord_music_player.application.interfaces.ai_client import AIClient
from discord_music_player.config.settings import AISettings
from discord_music_player.domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
)
from discord_music_player.domain.shared.messages import LogTemplates

# ============================================================================
# Pydantic Models for AI Response Validation
# ============================================================================


class AIRecommendationItem(BaseModel):
    """Schema for a single recommendation from the AI.

    This model validates and normalizes AI responses, making testing trivial:
    just create instances directly without calling the API.
    """

    title: str = Field(..., min_length=1, description="Song title")
    artist: str | None = Field(None, description="Artist name")
    query: str = Field("", description="YouTube search query")
    url: str | None = Field(None, description="Direct YouTube URL if known")

    def to_domain(self) -> Recommendation:
        """Convert to domain Recommendation entity."""
        query = self.query or f"{self.artist or ''} {self.title}".strip()
        return Recommendation(
            title=self.title,
            artist=self.artist,
            query=query,
            url=self.url,
        )


class AIRecommendationResponse(BaseModel):
    """Schema for the full AI recommendation response.

    OpenAI will return this exact structure thanks to response_format.
    """

    recs: list[AIRecommendationItem] = Field(
        default_factory=list, description="List of song recommendations"
    )

    def to_domain_list(self) -> list[Recommendation]:
        """Convert all items to domain Recommendation entities."""
        return [item.to_domain() for item in self.recs]


logger = logging.getLogger(__name__)

# Timeout and retry settings
OPENAI_TIMEOUT: float = 20.0
MAX_ATTEMPTS: int = 1
BACKOFF_BASE: float = 0.35


@dataclass
class CacheEntry:
    """Cache entry with timestamp for expiration."""

    data: list[dict[str, Any]]
    created_at: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if this cache entry has expired."""
        return (time.time() - self.created_at) > ttl_seconds


def _jitter(n: int) -> float:
    """Calculate backoff with jitter for retry."""
    return BACKOFF_BASE * (2 ** (n - 1)) + random.random() * 0.2


class OpenAIRecommendationClient(AIClient):
    """OpenAI-based recommendation client.

    Handles AI-powered track recommendations with caching,
    rate limiting, and proper error handling.
    """

    def __init__(self, settings: AISettings | None = None) -> None:
        """Initialize the OpenAI client.

        Args:
            settings: AI settings for configuration.
        """
        self._settings = settings or AISettings()
        self._client: AsyncOpenAI | None = None

        self._cache: dict[str, CacheEntry] = {}
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Singleflight for request deduplication
        self._inflight: dict[str, asyncio.Future[list[dict[str, Any]]]] = {}

    def _get_client(self) -> AsyncOpenAI:
        """Get or create the OpenAI client lazily."""
        if self._client is not None:
            return self._client

        api_key_value = self._settings.api_key.get_secret_value()
        if not api_key_value:
            raise RuntimeError("OPENAI_API_KEY is not set; AI recommender is disabled.")

        self._client = AsyncOpenAI(api_key=api_key_value, max_retries=0)
        logger.info(LogTemplates.AI_CLIENT_INITIALIZED, self._settings.model, OPENAI_TIMEOUT)
        return self._client

    def _cache_key(self, request: RecommendationRequest) -> str:
        """Build a cache key from a recommendation request."""
        title = request.base_track_title.strip().lower()
        artist = (request.base_track_artist or "").strip().lower()
        return f"{title}|{artist}|{request.count}|{self._settings.model}"

    async def _call_api(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Make an API call with retry logic.

        Args:
            messages: Message list for the API.

        Returns:
            Parsed JSON response.
        """
        client = self._get_client()
        last_exc: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._execute_api_call(client, messages)
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(LogTemplates.AI_RESPONSE_PARSE_ERROR, e)
                raise
            except Exception as e:
                last_exc = await self._handle_api_error(e, attempt)

        raise last_exc or RuntimeError("Unknown AI failure")

    async def _execute_api_call(
        self, client: AsyncOpenAI, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Execute a single API call and parse the response."""
        response = await client.with_options(timeout=OPENAI_TIMEOUT).chat.completions.create(
            model=self._settings.model,
            messages=messages,  # type: ignore
            max_tokens=self._settings.max_tokens,
            temperature=self._settings.temperature,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from API")

        return json.loads(content)

    async def _handle_api_error(self, error: Exception, attempt: int) -> Exception:
        """Handle API error with logging and backoff."""
        is_retryable = isinstance(
            error,
            (
                APITimeoutError,
                APIConnectionError,
                RateLimitError,
                APIStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ),
        )

        if is_retryable:
            logger.warning(
                LogTemplates.AI_API_ERROR_RETRY,
                attempt,
                MAX_ATTEMPTS,
                error.__class__.__name__,
            )
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(_jitter(attempt))
            return error

        raise error

    async def _fetch_recommendations_raw(
        self, request: RecommendationRequest
    ) -> list[dict[str, Any]]:
        """Fetch raw recommendations from API with caching and singleflight.

        Args:
            request: The recommendation request.

        Returns:
            List of raw recommendation dictionaries.
        """
        cache_key = self._cache_key(request)

        # Check cache first
        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if not entry.is_expired(self._settings.cache_ttl_seconds):
                self._cache_hits += 1
                logger.debug(LogTemplates.CACHE_HIT, request.base_track_title)
                return entry.data
            else:
                # Clean up expired entry
                del self._cache[cache_key]

        self._cache_misses += 1

        # Singleflight: check if request is already in-flight
        if cache_key in self._inflight:
            logger.debug(LogTemplates.CACHE_JOIN_INFLIGHT, request.base_track_title)
            return await self._inflight[cache_key]

        # Create future for other callers to join
        future: asyncio.Future[list[dict[str, Any]]] = asyncio.Future()
        self._inflight[cache_key] = future

        try:
            # Build prompt
            system = (
                "You are a music recommender. Respond with STRICT JSON (no markdown). "
                'Schema: {"recs": [{"title": string, "artist": string, '
                '"query": string, "url": string|null}]}. '
                "Rules:\n"
                "- Return EXACTLY the requested number of items.\n"
                "- Similar vibe/genre/era/energy to the base track.\n"
                "- Avoid recommending the same track as the base.\n"
                "- Prefer queries that uniquely resolve on YouTube.\n"
                "- If unsure about a URL, set url to null.\n"
                "- No extra text outside the JSON object."
            )

            user = (
                f"Count: {request.count}\n"
                f"Base title: {request.base_track_title}\n"
                f"Base artist: {request.base_track_artist or ''}\n"
                "Return only the JSON object."
            )

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]

            logger.debug(
                LogTemplates.AI_FETCHING_RECOMMENDATIONS, request.base_track_title, request.count
            )

            data = await self._call_api(messages)

            # Parse response
            recs = data.get("recs", [])
            if not isinstance(recs, list):
                recs = []

            # Cache the result
            self._cache[cache_key] = CacheEntry(data=recs)

            # Resolve the future
            future.set_result(recs)

            logger.debug(
                LogTemplates.AI_GENERATED_RECOMMENDATIONS, len(recs), request.base_track_title
            )

            return recs

        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            # Clean up in-flight tracker
            self._inflight.pop(cache_key, None)

    async def get_recommendations(self, request: RecommendationRequest) -> list[Recommendation]:
        """Get track recommendations based on a request.

        Args:
            request: The recommendation request with base track info.

        Returns:
            List of recommendations.
        """
        try:
            raw_recs = await self._fetch_recommendations_raw(request)

            # Use Pydantic for validated parsing (model_validate handles dict coercion)
            response = AIRecommendationResponse.model_validate({"recs": raw_recs})
            recommendations = response.to_domain_list()

            return recommendations[: request.count]

        except Exception as e:
            logger.error(LogTemplates.AI_REQUEST_FAILED, e)
            return []

    async def is_available(self) -> bool:
        """Check if the AI service is available.

        Returns:
            True if the service can accept requests.
        """
        if not self._settings.api_key.get_secret_value():
            return False

        try:
            self._get_client()
            return True
        except Exception:
            return False

    def clear_cache(self) -> int:
        """Clear the recommendation cache.

        Returns:
            Number of entries cleared.
        """
        count = len(self._cache)
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        logger.info(LogTemplates.CACHE_CLEARED, count)
        return count

    def prune_cache(self, max_age_seconds: int) -> int:
        """Remove old cache entries.

        Args:
            max_age_seconds: Maximum age of entries to keep.

        Returns:
            Number of entries pruned.
        """
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
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (hits, misses, size, etc.)
        """
        return {
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "hit_rate": int(
                (self._cache_hits / max(1, self._cache_hits + self._cache_misses)) * 100
            ),
            "inflight": len(self._inflight),
        }
