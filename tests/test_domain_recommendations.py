"""
Unit Tests for Domain Recommendations Layer

Tests for:
- Entities: RecommendationRequest, Recommendation, RecommendationSet
- Services: RecommendationDomainService
"""

from datetime import UTC, datetime, timedelta

import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.recommendations.entities import (
    MAX_RECOMMENDATION_COUNT,
    Recommendation,
    RecommendationRequest,
    RecommendationSet,
)
from discord_music_player.domain.recommendations.services import RecommendationDomainService

# =============================================================================
# RecommendationRequest Entity Tests
# =============================================================================


class TestRecommendationRequest:
    """Unit tests for RecommendationRequest entity."""

    def test_create_minimal_request(self):
        """Should create request with required fields only."""
        request = RecommendationRequest(base_track_title="Test Song")
        assert request.base_track_title == "Test Song"
        assert request.base_track_artist is None
        assert request.count == 3

    def test_create_full_request(self):
        """Should create request with all fields."""
        request = RecommendationRequest(
            base_track_title="Test Song",
            base_track_artist="Test Artist",
            count=5,
            genre_hint="rock",
            exclude_tracks=frozenset(["id1", "id2"]),
        )
        assert request.base_track_title == "Test Song"
        assert request.base_track_artist == "Test Artist"
        assert request.count == 5
        assert request.genre_hint == "rock"
        assert "id1" in request.exclude_tracks

    def test_empty_title_raises_error(self):
        """Should raise ValueError for empty title."""
        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="")

    def test_count_below_one_raises_error(self):
        """Should raise ValueError for count < 1."""
        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="Test Song", count=0)

    def test_count_above_ten_raises_error(self):
        """Should raise ValueError for count > 10."""
        with pytest.raises(ValueError):
            RecommendationRequest(base_track_title="Test Song", count=11)

    def test_cache_key_generated(self):
        """Should generate normalized cache key."""
        request = RecommendationRequest(
            base_track_title="Test Song", base_track_artist="Test Artist", count=3
        )
        assert "test song" in request.cache_key
        assert "test artist" in request.cache_key
        assert "3" in request.cache_key

    def test_cache_key_without_artist(self):
        """Should handle missing artist in cache key."""
        request = RecommendationRequest(base_track_title="Test Song")
        assert "unknown" in request.cache_key


# =============================================================================
# Recommendation Entity Tests
# =============================================================================


class TestRecommendation:
    """Unit tests for Recommendation entity."""

    def test_create_minimal_recommendation(self):
        """Should create recommendation with title only."""
        rec = Recommendation(title="Test Song")
        assert rec.title == "Test Song"
        assert rec.query == "Test Song"  # Auto-generated
        assert rec.confidence == 1.0

    def test_create_full_recommendation(self):
        """Should create recommendation with all fields."""
        rec = Recommendation(
            title="Test Song",
            artist="Test Artist",
            query="test artist test song",
            url="https://youtube.com/watch?v=abc",
            confidence=0.9,
            reason="Similar genre",
        )
        assert rec.title == "Test Song"
        assert rec.artist == "Test Artist"
        assert rec.query == "test artist test song"
        assert rec.confidence == 0.9

    def test_empty_title_raises_error(self):
        """Should raise ValueError for empty title."""
        with pytest.raises(ValueError):
            Recommendation(title="")

    def test_auto_generate_query_with_artist(self):
        """Should auto-generate query from artist and title."""
        rec = Recommendation(title="Test Song", artist="Test Artist")
        assert rec.query == "Test Artist - Test Song"

    def test_auto_generate_query_without_artist(self):
        """Should use title as query when no artist."""
        rec = Recommendation(title="Test Song")
        assert rec.query == "Test Song"

    def test_confidence_must_be_valid(self):
        """Should raise ValueError for invalid confidence."""
        with pytest.raises(ValueError):
            Recommendation(title="Test", confidence=1.5)

        with pytest.raises(ValueError):
            Recommendation(title="Test", confidence=-0.1)

    def test_display_text_with_artist(self):
        """Should return artist - title format."""
        rec = Recommendation(title="Test Song", artist="Test Artist")
        assert rec.display_text == "Test Artist - Test Song"

    def test_display_text_without_artist(self):
        """Should return title only when no artist."""
        rec = Recommendation(title="Test Song")
        assert rec.display_text == "Test Song"


# =============================================================================
# RecommendationSet Entity Tests
# =============================================================================


class TestRecommendationSet:
    """Unit tests for RecommendationSet aggregate."""

    @pytest.fixture
    def sample_recommendations(self):
        """Fixture providing sample recommendations."""
        return [
            Recommendation(title="Song 1", artist="Artist 1", confidence=0.9),
            Recommendation(title="Song 2", artist="Artist 2", confidence=0.8),
            Recommendation(title="Song 3", artist="Artist 3", confidence=0.7),
        ]

    def test_create_empty_set(self):
        """Should create empty recommendation set."""
        rec_set = RecommendationSet(base_track_title="Base Song", base_track_artist="Base Artist")
        assert rec_set.base_track_title == "Base Song"
        assert rec_set.count == 0
        assert rec_set.is_empty is True

    def test_create_set_with_recommendations(self, sample_recommendations):
        """Should create set with recommendations."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=sample_recommendations,
        )
        assert rec_set.count == 3
        assert rec_set.is_empty is False

    def test_default_expiration_set(self):
        """Should set default expiration time."""
        rec_set = RecommendationSet(base_track_title="Base Song", base_track_artist="Base Artist")
        assert rec_set.expires_at is not None
        assert rec_set.expires_at > datetime.now(UTC)

    def test_is_expired_false_when_fresh(self):
        """Should not be expired when just created."""
        rec_set = RecommendationSet(base_track_title="Base Song", base_track_artist="Base Artist")
        assert rec_set.is_expired is False

    def test_is_expired_true_when_past(self):
        """Should be expired when past expiration."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            generated_at=datetime.now(UTC) - timedelta(hours=48),
            expires_at=datetime.now(UTC) - timedelta(hours=24),
        )
        assert rec_set.is_expired is True

    def test_add_recommendation(self):
        """Should add recommendation to set."""
        rec_set = RecommendationSet(base_track_title="Base Song", base_track_artist="Base Artist")
        rec = Recommendation(title="New Song", artist="New Artist")
        rec_set.add_recommendation(rec)
        assert rec_set.count == 1

    def test_get_queries(self, sample_recommendations):
        """Should return all search queries."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=sample_recommendations,
        )
        queries = rec_set.get_queries()
        assert len(queries) == 3

    def test_get_top_returns_sorted_by_confidence(self, sample_recommendations):
        """Should return top N by confidence."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=sample_recommendations,
        )
        top = rec_set.get_top(2)
        assert len(top) == 2
        assert top[0].confidence == 0.9
        assert top[1].confidence == 0.8

    def test_get_top_with_less_than_n(self, sample_recommendations):
        """Should return all when less than N available."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=sample_recommendations,
        )
        top = rec_set.get_top(10)
        assert len(top) == 3

    def test_cache_key_generated(self):
        """Should generate normalized cache key."""
        rec_set = RecommendationSet(base_track_title="Base Song", base_track_artist="Base Artist")
        assert "base song" in rec_set.cache_key
        assert "base artist" in rec_set.cache_key

    def test_from_request_factory(self, sample_recommendations):
        """Should create set from request and recommendations."""
        request = RecommendationRequest(
            base_track_title="Test Song", base_track_artist="Test Artist", count=3
        )
        rec_set = RecommendationSet.from_request(request, sample_recommendations)
        assert rec_set.base_track_title == "Test Song"
        assert rec_set.base_track_artist == "Test Artist"
        assert rec_set.count == 3


# =============================================================================
# RecommendationDomainService Tests
# =============================================================================


class TestRecommendationDomainService:
    """Unit tests for RecommendationDomainService."""

    @pytest.fixture
    def track(self):
        """Fixture providing a sample track."""
        return Track(
            id=TrackId("test123"),
            title="Artist Name - Song Title (Official Video)",
            webpage_url="https://youtube.com/watch?v=test123",
        )

    # --- create_request_from_track tests ---

    def test_create_request_from_track_basic(self, track):
        """Should create request from track."""
        request = RecommendationDomainService.create_request_from_track(track)
        assert isinstance(request, RecommendationRequest)
        assert request.count == 3  # Default

    def test_create_request_with_count(self, track):
        """Should respect custom count."""
        request = RecommendationDomainService.create_request_from_track(track, count=5)
        assert request.count == 5

    def test_create_request_caps_count(self, track):
        """Should cap count at MAX_RECOMMENDATION_COUNT."""
        request = RecommendationDomainService.create_request_from_track(track, count=100)
        assert request.count <= MAX_RECOMMENDATION_COUNT

    def test_create_request_with_exclude_ids(self, track):
        """Should include exclude IDs."""
        request = RecommendationDomainService.create_request_from_track(
            track, exclude_ids=["id1", "id2"]
        )
        assert "id1" in request.exclude_tracks
        assert "id2" in request.exclude_tracks

    # --- extract_artist_from_title tests ---

    def test_extract_artist_dash_format(self):
        """Should extract artist from 'Artist - Title' format."""
        artist = RecommendationDomainService.extract_artist_from_title("The Beatles - Yesterday")
        assert artist == "The Beatles"

    def test_extract_artist_by_format(self):
        """Should extract artist from 'Title by Artist' format."""
        artist = RecommendationDomainService.extract_artist_from_title("Yesterday by The Beatles")
        assert artist == "The Beatles"

    def test_extract_artist_by_format_with_brackets(self):
        """Should handle 'Title by Artist [metadata]' format."""
        artist = RecommendationDomainService.extract_artist_from_title(
            "Yesterday by The Beatles [Official Audio]"
        )
        assert artist == "The Beatles"

    def test_extract_artist_filters_common_prefixes(self):
        """Should filter common non-artist prefixes."""
        artist = RecommendationDomainService.extract_artist_from_title("VEVO - Song")
        assert artist is None

        artist = RecommendationDomainService.extract_artist_from_title("Official - Song")
        assert artist is None

    def test_extract_artist_returns_none_when_not_found(self):
        """Should return None when no artist pattern found."""
        artist = RecommendationDomainService.extract_artist_from_title("Just A Song Name")
        assert artist is None

    # --- clean_title tests ---

    def test_clean_title_removes_official_video(self):
        """Should remove (Official Video) suffix."""
        cleaned = RecommendationDomainService.clean_title("Song Title (Official Video)")
        assert "official video" not in cleaned.lower()
        assert "Song Title" in cleaned

    def test_clean_title_removes_lyrics(self):
        """Should remove [Lyrics] suffix."""
        cleaned = RecommendationDomainService.clean_title("Song Title [Lyrics]")
        assert "lyrics" not in cleaned.lower()
        assert "Song Title" in cleaned

    def test_clean_title_removes_hd_hq(self):
        """Should remove quality markers."""
        cleaned = RecommendationDomainService.clean_title("Song Title (HD)")
        assert "hd" not in cleaned.lower()

        cleaned = RecommendationDomainService.clean_title("Song Title [HQ]")
        assert "hq" not in cleaned.lower()

    def test_clean_title_removes_feat(self):
        """Should remove featuring credits."""
        cleaned = RecommendationDomainService.clean_title("Song Title (ft. Other Artist)")
        assert "ft." not in cleaned.lower()

        cleaned = RecommendationDomainService.clean_title("Song Title (feat. Other Artist)")
        assert "feat." not in cleaned.lower()

    def test_clean_title_removes_remaster(self):
        """Should remove remaster tags."""
        cleaned = RecommendationDomainService.clean_title("Song Title (Remastered)")
        assert "remaster" not in cleaned.lower()

    def test_clean_title_removes_multiple_suffixes(self):
        """Should remove multiple suffixes."""
        cleaned = RecommendationDomainService.clean_title(
            "Song Title (Official Video) [Lyrics] (HD)"
        )
        assert "official video" not in cleaned.lower()
        assert "lyrics" not in cleaned.lower()
        assert "hd" not in cleaned.lower()

    def test_clean_title_preserves_core_title(self):
        """Should preserve the core title."""
        cleaned = RecommendationDomainService.clean_title("Artist - Song Title (Official Video)")
        assert "Artist - Song Title" in cleaned

    # --- filter_duplicates tests ---

    def test_filter_duplicates_removes_exact_duplicates(self):
        """Should remove exact duplicates."""
        recs = [
            Recommendation(title="Song", artist="Artist"),
            Recommendation(title="Song", artist="Artist"),
            Recommendation(title="Another", artist="Artist"),
        ]
        filtered = RecommendationDomainService.filter_duplicates(recs)
        assert len(filtered) == 2

    def test_filter_duplicates_case_insensitive(self):
        """Should treat different cases as duplicates."""
        recs = [
            Recommendation(title="Song", artist="Artist"),
            Recommendation(title="SONG", artist="ARTIST"),
        ]
        filtered = RecommendationDomainService.filter_duplicates(recs)
        assert len(filtered) == 1

    def test_filter_duplicates_preserves_order(self):
        """Should preserve order (keep first occurrence)."""
        recs = [
            Recommendation(title="First", artist="A", confidence=0.5),
            Recommendation(title="Second", artist="B", confidence=0.9),
            Recommendation(title="First", artist="A", confidence=0.8),
        ]
        filtered = RecommendationDomainService.filter_duplicates(recs)
        assert len(filtered) == 2
        assert filtered[0].title == "First"
        assert filtered[0].confidence == 0.5  # First occurrence kept

    def test_filter_duplicates_empty_list(self):
        """Should handle empty list."""
        filtered = RecommendationDomainService.filter_duplicates([])
        assert filtered == []

    # --- validate_recommendations tests ---

    def test_validate_valid_set(self):
        """Should return no errors for valid set."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=[
                Recommendation(title="Song 1", artist="Artist 1"),
                Recommendation(title="Song 2", artist="Artist 2"),
            ],
        )
        errors = RecommendationDomainService.validate_recommendations(rec_set)
        assert len(errors) == 0

    def test_validate_empty_set(self):
        """Should return error for empty set."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=[],
        )
        errors = RecommendationDomainService.validate_recommendations(rec_set)
        assert any("No recommendations" in e for e in errors)

    def test_validate_expired_set(self):
        """Should return error for expired set."""
        rec_set = RecommendationSet(
            base_track_title="Base Song",
            base_track_artist="Base Artist",
            recommendations=[Recommendation(title="Song", artist="Artist")],
            generated_at=datetime.now(UTC) - timedelta(hours=48),
            expires_at=datetime.now(UTC) - timedelta(hours=24),
        )
        errors = RecommendationDomainService.validate_recommendations(rec_set)
        assert any("expired" in e.lower() for e in errors)


# =============================================================================
# Integration between Request and Set
# =============================================================================


class TestRecommendationIntegration:
    """Integration tests for recommendation entities working together."""

    def test_full_workflow(self):
        """Test complete workflow: request -> recommendations -> set."""
        # Create request
        request = RecommendationRequest(
            base_track_title="Test Song", base_track_artist="Test Artist", count=3
        )

        # Simulate AI recommendations
        recommendations = [
            Recommendation(title="Similar Song 1", artist="Artist 1", confidence=0.95),
            Recommendation(title="Similar Song 2", artist="Artist 2", confidence=0.85),
            Recommendation(title="Similar Song 3", artist="Artist 3", confidence=0.75),
        ]

        # Create set from request and recommendations
        rec_set = RecommendationSet.from_request(request, recommendations)

        # Validate
        errors = RecommendationDomainService.validate_recommendations(rec_set)
        assert len(errors) == 0

        # Get top recommendations
        top = rec_set.get_top(2)
        assert len(top) == 2
        assert top[0].confidence == 0.95

    def test_cache_key_consistency(self):
        """Cache keys should be consistent between request and set."""
        request = RecommendationRequest(
            base_track_title="Test Song", base_track_artist="Test Artist", count=3
        )

        rec_set = RecommendationSet.from_request(request, [])

        # Cache keys should have same base (title|artist)
        # Request includes count, set doesn't
        assert "test song" in request.cache_key
        assert "test song" in rec_set.cache_key
        assert "test artist" in request.cache_key
        assert "test artist" in rec_set.cache_key
