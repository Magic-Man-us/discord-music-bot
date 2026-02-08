"""
Tests for AI Recommendation Client.

Demonstrates how Pydantic models make AI response testing trivial:
- No API mocking required for parsing logic
- Direct model construction for unit tests
- Clear validation error messages
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discord_music_player.config.settings import AISettings
from discord_music_player.domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
)
from discord_music_player.infrastructure.ai.recommendation_client import (
    AIRecommendationClient,
    AIRecommendationItem,
    AIRecommendationResponse,
)

# ============================================================================
# Pydantic Model Tests - No API Calls Required!
# ============================================================================


class TestAIRecommendationItem:
    """Tests for AIRecommendationItem Pydantic model."""

    def test_valid_item_with_all_fields(self) -> None:
        """Test creating a fully populated recommendation item."""
        item = AIRecommendationItem(
            title="Bohemian Rhapsody",
            artist="Queen",
            query="Queen Bohemian Rhapsody",
            url="https://youtube.com/watch?v=fJ9rUzIMcZQ",
        )

        assert item.title == "Bohemian Rhapsody"
        assert item.artist == "Queen"
        assert item.query == "Queen Bohemian Rhapsody"
        assert item.url == "https://youtube.com/watch?v=fJ9rUzIMcZQ"

    def test_item_with_only_title(self) -> None:
        """Test creating item with only required title field."""
        item = AIRecommendationItem(title="Hotel California")

        assert item.title == "Hotel California"
        assert item.artist is None
        assert item.query == ""  # Default
        assert item.url is None

    def test_to_domain_with_query(self) -> None:
        """Test conversion to domain Recommendation with explicit query."""
        item = AIRecommendationItem(
            title="Stairway to Heaven",
            artist="Led Zeppelin",
            query="Led Zeppelin Stairway to Heaven official",
        )

        rec = item.to_domain()

        assert isinstance(rec, Recommendation)
        assert rec.title == "Stairway to Heaven"
        assert rec.artist == "Led Zeppelin"
        assert rec.query == "Led Zeppelin Stairway to Heaven official"

    def test_to_domain_generates_query(self) -> None:
        """Test that to_domain() generates query if not provided."""
        item = AIRecommendationItem(
            title="Comfortably Numb",
            artist="Pink Floyd",
            query="",  # Empty
        )

        rec = item.to_domain()

        assert rec.query == "Pink Floyd Comfortably Numb"

    def test_to_domain_without_artist(self) -> None:
        """Test query generation when artist is None."""
        item = AIRecommendationItem(
            title="Thunderstruck",
            artist=None,
            query="",
        )

        rec = item.to_domain()

        assert rec.query == "Thunderstruck"

    def test_empty_title_fails_validation(self) -> None:
        """Test that empty title fails Pydantic validation."""
        with pytest.raises(ValueError):
            AIRecommendationItem(title="")


class TestAIRecommendationResponse:
    """Tests for AIRecommendationResponse Pydantic model."""

    def test_empty_response(self) -> None:
        """Test creating response with no recommendations."""
        response = AIRecommendationResponse(recs=[])

        assert response.recs == []
        assert response.to_domain_list() == []

    def test_response_with_items(self) -> None:
        """Test creating response with multiple items."""
        response = AIRecommendationResponse(
            recs=[
                AIRecommendationItem(title="Song 1", artist="Artist 1"),
                AIRecommendationItem(title="Song 2", artist="Artist 2"),
                AIRecommendationItem(title="Song 3"),
            ]
        )

        assert len(response.recs) == 3

        domain_list = response.to_domain_list()
        assert len(domain_list) == 3
        assert all(isinstance(r, Recommendation) for r in domain_list)

    def test_model_validate_from_dict(self) -> None:
        """Test creating response from raw dict (simulating API response)."""
        raw_data = {
            "recs": [
                {"title": "Yesterday", "artist": "The Beatles", "query": "Beatles Yesterday"},
                {"title": "Imagine", "artist": "John Lennon"},
            ]
        }

        response = AIRecommendationResponse.model_validate(raw_data)

        assert len(response.recs) == 2
        assert response.recs[0].title == "Yesterday"
        assert response.recs[1].artist == "John Lennon"

    def test_model_validate_handles_partial_items(self) -> None:
        """Test that partial items (missing optional fields) work."""
        raw_data = {
            "recs": [
                {"title": "Song A"},  # Only title
                {"title": "Song B", "url": "http://example.com"},  # Title + URL
            ]
        }

        response = AIRecommendationResponse.model_validate(raw_data)

        assert response.recs[0].artist is None
        assert response.recs[1].url == "http://example.com"

    def test_model_validate_with_extra_fields_ignored(self) -> None:
        """Test that extra fields from AI are ignored."""
        raw_data = {
            "recs": [
                {
                    "title": "Song",
                    "artist": "Artist",
                    "unknown_field": "ignored",
                    "another_extra": 123,
                }
            ]
        }

        # Should not raise - extra fields are ignored by default
        response = AIRecommendationResponse.model_validate(raw_data)
        assert response.recs[0].title == "Song"


class TestRecommendationRequest:
    """Tests for RecommendationRequest domain entity."""

    def test_valid_request(self) -> None:
        """Test creating a valid recommendation request."""
        request = RecommendationRequest(
            base_track_title="Test Song",
            base_track_artist="Test Artist",
            count=5,
        )

        assert request.base_track_title == "Test Song"
        assert request.base_track_artist == "Test Artist"
        assert request.count == 5

    def test_request_defaults(self) -> None:
        """Test request default values."""
        request = RecommendationRequest(base_track_title="Test")

        assert request.count == 3  # Default
        assert request.base_track_artist is None

    def test_cache_key_generation(self) -> None:
        """Test cache key is deterministic and normalized."""
        request1 = RecommendationRequest(
            base_track_title="Hello World",
            base_track_artist="Test Artist",
            count=3,
        )
        request2 = RecommendationRequest(
            base_track_title="HELLO WORLD",  # Different case
            base_track_artist="TEST ARTIST",
            count=3,
        )

        # Cache keys should be case-insensitive
        assert request1.cache_key == request2.cache_key

    def test_empty_title_fails(self) -> None:
        """Test that empty title fails validation."""
        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="")

    def test_count_bounds(self) -> None:
        """Test count validation bounds."""
        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="Test", count=0)

        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="Test", count=11)


# ============================================================================
# AIRecommendationClient Tests
# ============================================================================


@pytest.fixture
def mock_settings():
    """Create mock AI settings."""
    return AISettings(
        model="openai:gpt-4o-mini",
        max_tokens=500,
        temperature=0.7,
        cache_ttl_seconds=300,
    )


@pytest.fixture
def client(mock_settings):
    """Create AI client with mock settings."""
    return AIRecommendationClient(mock_settings)


@pytest.fixture
def sample_request():
    """Create a sample recommendation request."""
    return RecommendationRequest(
        base_track_title="Bohemian Rhapsody",
        base_track_artist="Queen",
        count=3,
    )


class TestClientInitialization:
    """Tests for client initialization."""

    def test_init_with_settings(self, mock_settings):
        """Should initialize with provided settings."""
        client = AIRecommendationClient(mock_settings)
        assert client._settings == mock_settings
        assert client._agent is None  # Lazy initialization

    def test_init_without_settings(self):
        """Should initialize with default settings."""
        with patch(
            "discord_music_player.infrastructure.ai.recommendation_client.AISettings"
        ) as mock_ai_settings:
            client = AIRecommendationClient()
            mock_ai_settings.assert_called_once()

    def test_lazy_agent_creation(self, client):
        """Should create Agent lazily on first access."""
        assert client._agent is None
        with patch(
            "discord_music_player.infrastructure.ai.recommendation_client.Agent"
        ) as mock_agent:
            client._get_agent()
            mock_agent.assert_called_once()


class TestCacheKey:
    """Tests for cache key generation."""

    def test_cache_key_normalization(self, client):
        """Should normalize cache keys (lowercase, trimmed)."""
        request1 = RecommendationRequest(
            base_track_title="  Test Song  ",
            base_track_artist="  Test Artist  ",
            count=3,
        )
        request2 = RecommendationRequest(
            base_track_title="TEST SONG",
            base_track_artist="TEST ARTIST",
            count=3,
        )

        key1 = client._cache_key(request1)
        key2 = client._cache_key(request2)

        assert key1 == key2

    def test_cache_key_includes_count(self, client):
        """Should include count in cache key."""
        request1 = RecommendationRequest(base_track_title="Test", count=3)
        request2 = RecommendationRequest(base_track_title="Test", count=5)

        assert client._cache_key(request1) != client._cache_key(request2)

    def test_cache_key_includes_model(self, client):
        """Should include model in cache key."""
        request = RecommendationRequest(base_track_title="Test")
        key = client._cache_key(request)

        assert client._settings.model in key


class TestCaching:
    """Tests for caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_hit(self, client, sample_request):
        """Should use cached result on second call."""
        mock_response = AIRecommendationResponse(
            recs=[AIRecommendationItem(title="Song 1", artist="Artist 1")]
        )

        # First call - cache miss
        with patch.object(client, "_call_api", return_value=mock_response):
            result1 = await client._fetch_recommendations_raw(sample_request)

        # Second call - cache hit (no API call)
        with patch.object(client, "_call_api") as mock_api:
            result2 = await client._fetch_recommendations_raw(sample_request)
            mock_api.assert_not_called()

        assert result1 == result2
        assert client._cache_hits == 1
        assert client._cache_misses == 1

    @pytest.mark.asyncio
    async def test_cache_expiry(self, client, sample_request):
        """Should refetch after cache expiry."""
        mock_response1 = AIRecommendationResponse(
            recs=[AIRecommendationItem(title="Song 1")]
        )
        mock_response2 = AIRecommendationResponse(
            recs=[AIRecommendationItem(title="Song 2")]
        )

        # First call
        with patch.object(client, "_call_api", return_value=mock_response1):
            await client._fetch_recommendations_raw(sample_request)

        # Expire the cache entry
        cache_key = client._cache_key(sample_request)
        client._cache[cache_key].created_at = time.time() - client._settings.cache_ttl_seconds - 1

        # Second call - should refetch
        with patch.object(client, "_call_api", return_value=mock_response2):
            result = await client._fetch_recommendations_raw(sample_request)

        assert result == [{"title": "Song 2", "artist": None, "query": "", "url": None}]

    @pytest.mark.asyncio
    async def test_singleflight_deduplication(self, client, sample_request):
        """Should deduplicate concurrent requests for same cache key."""
        mock_response = AIRecommendationResponse(
            recs=[AIRecommendationItem(title="Song 1")]
        )
        api_call_count = 0

        async def mock_api_call(user_prompt):
            nonlocal api_call_count
            api_call_count += 1
            await asyncio.sleep(0.1)  # Simulate API delay
            return mock_response

        with patch.object(client, "_call_api", side_effect=mock_api_call):
            # Make 3 concurrent requests
            results = await asyncio.gather(
                client._fetch_recommendations_raw(sample_request),
                client._fetch_recommendations_raw(sample_request),
                client._fetch_recommendations_raw(sample_request),
            )

        # Should only call API once
        assert api_call_count == 1
        assert all(r == results[0] for r in results)


class TestAPICallHandling:
    """Tests for API call and error handling."""

    @pytest.mark.asyncio
    async def test_call_api_success(self, client):
        """Should execute API call and return structured response."""
        mock_response = AIRecommendationResponse(
            recs=[AIRecommendationItem(title="Test")]
        )
        mock_result = MagicMock()
        mock_result.output = mock_response

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)

        with patch.object(client, "_get_agent", return_value=mock_agent):
            result = await client._call_api("test prompt")

        assert result == mock_response

    @pytest.mark.asyncio
    async def test_call_api_error_raises(self, client):
        """Should raise error after logging."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=RuntimeError("API down"))

        with patch.object(client, "_get_agent", return_value=mock_agent):
            with pytest.raises(RuntimeError, match="API down"):
                await client._call_api("test prompt")

    def test_handle_api_error_logs_warning(self, client):
        """Should log warning for errors."""
        error = RuntimeError("some error")

        # Should not raise — just logs
        client._handle_api_error(error)


class TestGetRecommendations:
    """Tests for get_recommendations method."""

    @pytest.mark.asyncio
    async def test_get_recommendations_success(self, client, sample_request):
        """Should return recommendations from API."""
        mock_raw_recs = [
            {"title": "Song 1", "artist": "Artist 1", "query": "query 1"},
            {"title": "Song 2", "artist": "Artist 2", "query": "query 2"},
            {"title": "Song 3", "artist": "Artist 3", "query": "query 3"},
        ]

        with patch.object(client, "_fetch_recommendations_raw", return_value=mock_raw_recs):
            recs = await client.get_recommendations(sample_request)

        assert len(recs) == 3
        assert all(isinstance(r, Recommendation) for r in recs)
        assert recs[0].title == "Song 1"

    @pytest.mark.asyncio
    async def test_get_recommendations_limits_count(self, client):
        """Should limit results to requested count."""
        mock_raw_recs = [{"title": f"Song {i}", "artist": f"Artist {i}"} for i in range(5)]
        request = RecommendationRequest(base_track_title="Test", count=2)

        with patch.object(client, "_fetch_recommendations_raw", return_value=mock_raw_recs):
            recs = await client.get_recommendations(request)

        assert len(recs) == 2

    @pytest.mark.asyncio
    async def test_get_recommendations_handles_error(self, client, sample_request):
        """Should return empty list on error."""
        with patch.object(client, "_fetch_recommendations_raw", side_effect=Exception("API Error")):
            recs = await client.get_recommendations(sample_request)

        assert recs == []


class TestIsAvailable:
    """Tests for is_available method."""

    @pytest.mark.asyncio
    async def test_is_available_success(self, client):
        """Should return True when agent can be created."""
        with patch.object(client, "_get_agent"):
            available = await client.is_available()

        assert available is True

    @pytest.mark.asyncio
    async def test_is_available_handles_exception(self, client):
        """Should return False when agent creation fails."""
        with patch.object(client, "_get_agent", side_effect=Exception("Error")):
            available = await client.is_available()

        assert available is False


class TestCacheManagement:
    """Tests for cache management methods."""

    def test_clear_cache(self, client):
        """Should clear all cache entries."""
        # Add some cache entries
        client._cache["key1"] = MagicMock()
        client._cache["key2"] = MagicMock()
        client._cache_hits = 10
        client._cache_misses = 5

        count = client.clear_cache()

        assert count == 2
        assert len(client._cache) == 0
        assert client._cache_hits == 0
        assert client._cache_misses == 0

    def test_prune_cache_removes_old_entries(self, client):
        """Should remove entries older than specified age."""
        from discord_music_player.infrastructure.ai.recommendation_client import CacheEntry

        # Add entries with different ages
        client._cache["old1"] = CacheEntry(data=[], created_at=time.time() - 400)
        client._cache["old2"] = CacheEntry(data=[], created_at=time.time() - 500)
        client._cache["new"] = CacheEntry(data=[], created_at=time.time() - 100)

        count = client.prune_cache(max_age_seconds=300)

        assert count == 2
        assert "new" in client._cache
        assert "old1" not in client._cache
        assert "old2" not in client._cache

    def test_get_cache_stats(self, client):
        """Should return cache statistics."""
        client._cache["key1"] = MagicMock()
        client._cache["key2"] = MagicMock()
        client._cache_hits = 8
        client._cache_misses = 2

        stats = client.get_cache_stats()

        assert stats["size"] == 2
        assert stats["hits"] == 8
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 80
        assert "inflight" in stats

    def test_prune_cache_nothing_expired(self, client):
        """Should return 0 when no entries are expired."""
        from discord_music_player.infrastructure.ai.recommendation_client import CacheEntry

        client._cache["fresh"] = CacheEntry(data=[], created_at=time.time())

        count = client.prune_cache(max_age_seconds=300)

        assert count == 0
        assert "fresh" in client._cache


# ============================================================================
# Coverage Gap Tests
# ============================================================================


class TestGetAgentCaching:
    """Tests for _get_agent caching behavior."""

    def test_get_agent_returns_cached(self, client):
        """Should return cached agent on subsequent calls."""
        mock_agent = MagicMock()
        client._agent = mock_agent

        result = client._get_agent()

        assert result is mock_agent


class TestFetchRecommendationsRawEdgeCases:
    """Tests for _fetch_recommendations_raw edge cases."""

    @pytest.mark.asyncio
    async def test_exception_propagates_to_singleflight_future(self, client, sample_request):
        """Should propagate exception to waiting singleflight futures."""

        async def slow_failing_api(user_prompt):
            await asyncio.sleep(0.05)
            raise RuntimeError("API down")

        with patch.object(client, "_call_api", side_effect=slow_failing_api):
            results = await asyncio.gather(
                client._fetch_recommendations_raw(sample_request),
                client._fetch_recommendations_raw(sample_request),
                return_exceptions=True,
            )

        assert all(isinstance(r, RuntimeError) for r in results)
        # Inflight should be cleaned up
        assert len(client._inflight) == 0
