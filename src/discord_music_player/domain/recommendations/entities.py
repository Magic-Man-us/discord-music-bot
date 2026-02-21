"""Core domain entities for the recommendations bounded context."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Annotated, ClassVar, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from discord_music_player.domain.shared.datetime_utils import utcnow
from discord_music_player.domain.shared.types import HttpUrlStr, NonEmptyStr, PositiveInt, UnitInterval

if TYPE_CHECKING:
    from ..music.entities import Track

from .title_utils import clean_title, extract_artist_from_title  # noqa: E402

DEFAULT_RECOMMENDATION_COUNT: Final[int] = 3
MAX_RECOMMENDATION_COUNT: Final[int] = 10
DEFAULT_TOP_N: Final[int] = 3


class RecommendationRequest(BaseModel):
    """Value object for a recommendation request."""

    model_config = ConfigDict(frozen=True)

    base_track_title: NonEmptyStr
    base_track_artist: NonEmptyStr | None = None
    count: Annotated[PositiveInt, Field(le=MAX_RECOMMENDATION_COUNT)] = DEFAULT_RECOMMENDATION_COUNT
    genre_hint: NonEmptyStr | None = None
    exclude_tracks: frozenset[NonEmptyStr] = Field(default_factory=frozenset)

    @property
    def cache_key(self) -> str:
        artist = self.base_track_artist or "unknown"
        title_normalized = self.base_track_title.lower().strip()
        artist_normalized = artist.lower().strip()
        return f"{title_normalized}|{artist_normalized}|{self.count}"

    @classmethod
    def from_track(
        cls,
        track: Track,
        count: int = DEFAULT_RECOMMENDATION_COUNT,
        exclude_ids: list[str] | None = None,
    ) -> RecommendationRequest:
        """Build a recommendation request by parsing the track's title."""
        artist = extract_artist_from_title(track.title)
        title = clean_title(track.title)

        exclude_set = frozenset(exclude_ids) if exclude_ids else frozenset()

        return cls(
            base_track_title=title,
            base_track_artist=artist,
            count=min(count, MAX_RECOMMENDATION_COUNT),
            exclude_tracks=exclude_set,
        )


class Recommendation(BaseModel):
    """A single track recommendation that hasn't been resolved yet."""

    title: NonEmptyStr
    artist: NonEmptyStr | None = None
    query: str = ""  # Search query for resolution (set by model validator)
    url: HttpUrlStr | None = None  # Optional direct URL
    confidence: UnitInterval = 1.0  # Confidence score from AI
    reason: NonEmptyStr | None = None  # Why this was recommended

    @model_validator(mode="after")
    def _set_default_query(self) -> Recommendation:
        if not self.query:
            if self.artist:
                self.query = f"{self.artist} - {self.title}"
            else:
                self.query = self.title
        return self

    @property
    def display_text(self) -> str:
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title

    @property
    def dedup_key(self) -> str:
        """Lowercase artist|title key for duplicate detection."""
        return f"{(self.artist or '').lower()}|{self.title.lower()}"


class RecommendationSet(BaseModel):
    """Aggregate grouping recommendations for a specific base track."""

    base_track_title: NonEmptyStr
    base_track_artist: NonEmptyStr | None = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
    expires_at: datetime | None = None

    DEFAULT_CACHE_HOURS: ClassVar[int] = 24

    @model_validator(mode="after")
    def _set_default_expires_at(self) -> RecommendationSet:
        if self.expires_at is None:
            self.expires_at = self.generated_at + timedelta(hours=self.DEFAULT_CACHE_HOURS)
        return self

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utcnow() > self.expires_at

    @property
    def count(self) -> int:
        return len(self.recommendations)

    @property
    def is_empty(self) -> bool:
        return len(self.recommendations) == 0

    def add_recommendation(self, recommendation: Recommendation) -> None:
        self.recommendations.append(recommendation)

    def get_queries(self) -> list[str]:
        return [rec.query for rec in self.recommendations]

    def get_top(self, n: int = DEFAULT_TOP_N) -> list[Recommendation]:
        sorted_recs = sorted(self.recommendations, key=lambda r: r.confidence, reverse=True)
        return sorted_recs[:n]

    def deduplicate(self) -> int:
        """Remove duplicate recommendations in-place, return count removed."""
        seen: set[str] = set()
        unique: list[Recommendation] = []
        for rec in self.recommendations:
            if rec.dedup_key not in seen:
                seen.add(rec.dedup_key)
                unique.append(rec)
        removed = len(self.recommendations) - len(unique)
        self.recommendations = unique
        return removed

    def validate_set(self) -> list[str]:
        """Return error messages for invalid state (empty, expired, etc.)."""
        errors: list[str] = []
        if self.is_empty:
            errors.append("No recommendations in set")
        if self.is_expired:
            errors.append("Recommendation set has expired")
        return errors

    @property
    def cache_key(self) -> str:
        artist = self.base_track_artist or "unknown"
        title_normalized = self.base_track_title.lower().strip()
        artist_normalized = artist.lower().strip()
        return f"{title_normalized}|{artist_normalized}"

    @classmethod
    def from_request(
        cls, request: RecommendationRequest, recommendations: list[Recommendation]
    ) -> RecommendationSet:
        return cls(
            base_track_title=request.base_track_title,
            base_track_artist=request.base_track_artist,
            recommendations=recommendations,
        )
