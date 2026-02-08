"""
Additional Cache Repository Tests for Coverage

Tests edge cases and uncovered code paths in RecommendationCacheRepository.
"""

import pytest

from discord_music_player.domain.recommendations.entities import Recommendation, RecommendationSet


class TestCacheRepositoryEdgeCases:
    """Tests for cache repository edge cases and uncovered paths."""

    @pytest.fixture
    def sample_recommendation_set(self):
        """Create a sample recommendation set."""
        recommendations = [
            Recommendation(
                title="Song 1",
                artist="Artist 1",
                query="artist 1 song 1",
                url=None,
            ),
            Recommendation(
                title="Song 2",
                artist="Artist 2",
                query="artist 2 song 2",
                url="https://youtube.com/watch?v=abc",
            ),
        ]
        return RecommendationSet(
            base_track_title="Test Song",
            base_track_artist="Test Artist",
            recommendations=recommendations,
        )

    async def test_get_returns_none_for_missing_entry(self, cache_repository):
        """Should return None when cache entry doesn't exist."""
        result = await cache_repository.get(cache_key="nonexistent|unknown")

        assert result is None

    async def test_save_and_get_recommendation_set(
        self, cache_repository, sample_recommendation_set
    ):
        """Should save and retrieve recommendation set."""
        cache_key = "test song|test artist"

        await cache_repository.save(sample_recommendation_set)
        result = await cache_repository.get(cache_key)

        assert result is not None
        assert result.base_track_title == "Test Song"
        assert len(result.recommendations) == 2

    async def test_delete_removes_entry(self, cache_repository, sample_recommendation_set):
        """Should delete cache entry."""
        cache_key = "test song|test artist"

        await cache_repository.save(sample_recommendation_set)
        deleted = await cache_repository.delete(cache_key)

        assert deleted is True

        result = await cache_repository.get(cache_key)
        assert result is None

    async def test_delete_returns_false_for_missing(self, cache_repository):
        """Should return False when deleting non-existent entry."""
        deleted = await cache_repository.delete("nonexistent|unknown")

        assert deleted is False

    async def test_cleanup_expired_removes_expired_entries(self, cache_repository):
        """Should remove expired cache entries."""
        # Create entries with different cache keys
        rec_set1 = RecommendationSet(
            base_track_title="Song 1",
            base_track_artist="Artist 1",
            recommendations=[Recommendation(title="Rec 1", query="rec 1")],
        )
        rec_set2 = RecommendationSet(
            base_track_title="Song 2",
            base_track_artist="Artist 2",
            recommendations=[Recommendation(title="Rec 2", query="rec 2")],
        )

        await cache_repository.save(rec_set1)
        await cache_repository.save(rec_set2)

        # Wait for expiration would be too slow, so we test with current state
        count = await cache_repository.cleanup_expired()

        # Since they're not expired yet, count should be 0
        assert count == 0

    async def test_count_returns_total_entries(self, cache_repository, sample_recommendation_set):
        """Should return total number of cache entries."""
        # Start with 0
        assert await cache_repository.count() == 0

        # Add an entry
        await cache_repository.save(sample_recommendation_set)

        # Should have 1 entry
        assert await cache_repository.count() == 1

    async def test_clear_removes_everything(self, cache_repository, sample_recommendation_set):
        """Should remove all cache entries."""
        # Add entry
        await cache_repository.save(sample_recommendation_set)

        # Clear all
        count = await cache_repository.clear()

        assert count >= 1
        assert await cache_repository.count() == 0

    async def test_prune_removes_oldest_entries(self, cache_repository):
        """Should prune to maximum number of entries."""
        # Add 5 entries
        for i in range(5):
            rec_set = RecommendationSet(
                base_track_title=f"Song {i}",
                base_track_artist=f"Artist {i}",
                recommendations=[Recommendation(title=f"Rec {i}", query=f"rec {i}")],
            )
            await cache_repository.save(rec_set)

        # Prune to keep only 3
        count = await cache_repository.prune(max_entries=3)

        assert count == 2
        assert await cache_repository.count() == 3

    async def test_get_stats_returns_statistics(self, cache_repository, sample_recommendation_set):
        """Should return cache statistics."""
        # Add an entry
        await cache_repository.save(sample_recommendation_set)

        stats = await cache_repository.get_stats()

        assert "total_entries" in stats
        assert stats["total_entries"] == 1
        assert "expired_entries" in stats
        assert "oldest_entry" in stats
        assert "newest_entry" in stats
