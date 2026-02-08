"""Domain services containing recommendation business logic."""

import re
from typing import TYPE_CHECKING

from .entities import (
    Recommendation,
    RecommendationRequest,
    RecommendationSet,
)

if TYPE_CHECKING:
    from ..music.entities import Track


class RecommendationDomainService:
    """Recommendation-related business rules and transformations."""

    DEFAULT_RECOMMENDATION_COUNT = 3
    MAX_RECOMMENDATION_COUNT = 10

    @classmethod
    def create_request_from_track(
        cls,
        track: "Track",
        count: int = DEFAULT_RECOMMENDATION_COUNT,
        exclude_ids: list[str] | None = None,
    ) -> RecommendationRequest:
        artist = cls.extract_artist_from_title(track.title)
        title = cls.clean_title(track.title)

        exclude_set = frozenset(exclude_ids) if exclude_ids else frozenset()

        return RecommendationRequest(
            base_track_title=title,
            base_track_artist=artist,
            count=min(count, cls.MAX_RECOMMENDATION_COUNT),
            exclude_tracks=exclude_set,
        )

    @classmethod
    def extract_artist_from_title(cls, title: str) -> str | None:
        """Try to extract artist name from a track title.

        Common formats:
        - "Artist - Song Title"
        - "Artist: Song Title"
        - "Song Title by Artist"
        """
        if " - " in title:
            parts = title.split(" - ", 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                if not cls._is_common_prefix(artist):
                    return artist

        by_match = re.search(r"\s+by\s+(.+?)(?:\s*[\[\(]|$)", title, re.IGNORECASE)
        if by_match:
            return by_match.group(1).strip()

        return None

    @classmethod
    def clean_title(cls, title: str) -> str:
        """Remove common suffixes like "(Official Video)", "[Lyrics]", etc."""
        patterns = [
            r"\s*[\[\(](official\s*(video|audio|music\s*video|lyric\s*video|visualizer))\s*[\]\)]",
            r"\s*[\[\(](lyrics?|with\s*lyrics?|letra)\s*[\]\)]",
            r"\s*[\[\(](hd|hq|4k|1080p|720p)\s*[\]\)]",
            r"\s*[\[\(](audio)\s*[\]\)]",
            r"\s*[\[\(](remaster(ed)?|remix)\s*[\]\)]",
            r"\s*[\[\(](ft\.?|feat\.?|featuring)\s+[^\]\)]+[\]\)]",
        ]

        result = title
        for pattern in patterns:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)

        return result.strip()

    @classmethod
    def _is_common_prefix(cls, text: str) -> bool:
        """Check if text is a common non-artist prefix."""
        common_prefixes = {
            "official",
            "vevo",
            "music",
            "audio",
            "video",
            "topic",
            "lyrics",
            "lyric",
            "hd",
            "hq",
        }
        return text.lower() in common_prefixes

    @classmethod
    def filter_duplicates(cls, recommendations: list[Recommendation]) -> list[Recommendation]:
        seen_keys: set[str] = set()
        unique: list[Recommendation] = []

        for rec in recommendations:
            key = f"{(rec.artist or '').lower()}|{rec.title.lower()}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(rec)

        return unique

    @classmethod
    def validate_recommendations(cls, recommendation_set: RecommendationSet) -> list[str]:
        """Validate a recommendation set, returning error messages."""
        errors: list[str] = []

        if recommendation_set.is_empty:
            errors.append("No recommendations in set")

        if recommendation_set.is_expired:
            errors.append("Recommendation set has expired")

        return errors
