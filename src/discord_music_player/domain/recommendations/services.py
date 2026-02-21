"""Domain services containing recommendation business logic.

Thin service that delegates to entity methods and title utilities.
Most logic now lives on the Pydantic models themselves:
- ``RecommendationRequest.from_track()`` — build request from a Track
- ``RecommendationSet.deduplicate()`` — remove duplicate recommendations
- ``RecommendationSet.validate_set()`` — check for empty / expired state

The classmethods below are kept as a stable public API so that existing
call-sites (radio_service, tests) don't break.  They forward to the models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .entities import (
    DEFAULT_RECOMMENDATION_COUNT,
    Recommendation,
    RecommendationRequest,
    RecommendationSet,
)
from .title_utils import clean_title, extract_artist_from_title

if TYPE_CHECKING:
    from ..music.entities import Track


class RecommendationDomainService:
    """Recommendation-related business rules and transformations.

    Delegates to entity methods; kept for backward-compatible call-sites.
    """

    # ── Forwarding helpers (stable public API) ─────────────────────────

    @classmethod
    def create_request_from_track(
        cls,
        track: Track,
        count: int = DEFAULT_RECOMMENDATION_COUNT,
        exclude_ids: list[str] | None = None,
    ) -> RecommendationRequest:
        return RecommendationRequest.from_track(track, count=count, exclude_ids=exclude_ids)

    @staticmethod
    def extract_artist_from_title(title: str) -> str | None:
        return extract_artist_from_title(title)

    @staticmethod
    def clean_title(title: str) -> str:
        return clean_title(title)

    @staticmethod
    def filter_duplicates(recommendations: list[Recommendation]) -> list[Recommendation]:
        """Deduplicate a free-standing list (not yet in a RecommendationSet)."""
        seen: set[str] = set()
        unique: list[Recommendation] = []
        for rec in recommendations:
            if rec.dedup_key not in seen:
                seen.add(rec.dedup_key)
                unique.append(rec)
        return unique

    @staticmethod
    def validate_recommendations(recommendation_set: RecommendationSet) -> list[str]:
        return recommendation_set.validate_set()
