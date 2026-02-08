"""
Recommendations Domain Entities

Core domain entities for the recommendations bounded context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.messages import ErrorMessages


@dataclass(frozen=True)
class RecommendationRequest:
    """Value object for a recommendation request.

    Contains the information needed to generate recommendations.
    """

    base_track_title: str
    base_track_artist: str | None = None
    count: int = 3
    genre_hint: str | None = None
    exclude_tracks: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.base_track_title:
            raise ValueError(ErrorMessages.EMPTY_BASE_TRACK_TITLE)
        if self.count < 1:
            raise ValueError(ErrorMessages.INVALID_RECOMMENDATION_COUNT_MIN)
        if self.count > 10:
            raise ValueError(ErrorMessages.INVALID_RECOMMENDATION_COUNT_MAX)

    @property
    def cache_key(self) -> str:
        """Generate a cache key for this request."""
        artist = self.base_track_artist or "unknown"
        # Normalize for caching
        title_normalized = self.base_track_title.lower().strip()
        artist_normalized = artist.lower().strip()
        return f"{title_normalized}|{artist_normalized}|{self.count}"


@dataclass
class Recommendation:
    """Domain entity for a single track recommendation.

    Represents a recommended track that hasn't been resolved yet.
    """

    title: str
    artist: str | None = None
    query: str = ""  # Search query for resolution
    url: str | None = None  # Optional direct URL
    confidence: float = 1.0  # Confidence score from AI
    reason: str | None = None  # Why this was recommended

    def __post_init__(self) -> None:
        if not self.title:
            raise ValueError(ErrorMessages.EMPTY_RECOMMENDATION_TITLE)
        if not self.query:
            # Generate default search query
            if self.artist:
                self.query = f"{self.artist} - {self.title}"
            else:
                self.query = self.title
        if not 0 <= self.confidence <= 1:
            raise ValueError(ErrorMessages.INVALID_CONFIDENCE)

    @property
    def display_text(self) -> str:
        """Get display text for this recommendation."""
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title


@dataclass
class RecommendationSet:
    """Aggregate for a set of recommendations.

    Groups recommendations for a specific base track.
    """

    base_track_title: str
    base_track_artist: str | None
    recommendations: list[Recommendation] = field(default_factory=list)
    generated_at: datetime = field(default_factory=utcnow)
    expires_at: datetime = field(default_factory=lambda: utcnow() + timedelta(hours=24))

    # Default cache duration
    DEFAULT_CACHE_HOURS = 24

    def __post_init__(self) -> None:
        if self.expires_at is None:
            self.expires_at = self.generated_at + timedelta(hours=self.DEFAULT_CACHE_HOURS)

    @property
    def is_expired(self) -> bool:
        """Check if this recommendation set has expired."""
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at

    @property
    def count(self) -> int:
        """Get the number of recommendations."""
        return len(self.recommendations)

    @property
    def is_empty(self) -> bool:
        """Check if there are no recommendations."""
        return len(self.recommendations) == 0

    def add_recommendation(self, recommendation: Recommendation) -> None:
        """Add a recommendation to the set."""
        self.recommendations.append(recommendation)

    def get_queries(self) -> list[str]:
        """Get all search queries for the recommendations."""
        return [rec.query for rec in self.recommendations]

    def get_top(self, n: int = 3) -> list[Recommendation]:
        """Get the top N recommendations by confidence."""
        sorted_recs = sorted(self.recommendations, key=lambda r: r.confidence, reverse=True)
        return sorted_recs[:n]

    @property
    def cache_key(self) -> str:
        """Generate a cache key for this set."""
        artist = self.base_track_artist or "unknown"
        title_normalized = self.base_track_title.lower().strip()
        artist_normalized = artist.lower().strip()
        return f"{title_normalized}|{artist_normalized}"

    @classmethod
    def from_request(
        cls, request: RecommendationRequest, recommendations: list[Recommendation]
    ) -> RecommendationSet:
        """Create a recommendation set from a request and results."""
        return cls(
            base_track_title=request.base_track_title,
            base_track_artist=request.base_track_artist,
            recommendations=recommendations,
        )
