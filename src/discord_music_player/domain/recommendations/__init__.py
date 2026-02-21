"""
Recommendations Bounded Context

Domain logic for AI-powered track recommendations.
"""

from discord_music_player.domain.recommendations.entities import (
    Recommendation,
    RecommendationRequest,
    RecommendationSet,
)
from discord_music_player.domain.recommendations.repository import RecommendationCacheRepository
from discord_music_player.domain.recommendations.services import RecommendationDomainService
from discord_music_player.domain.recommendations.title_utils import clean_title, extract_artist_from_title

__all__ = [
    # Entities
    "Recommendation",
    "RecommendationRequest",
    "RecommendationSet",
    # Repository
    "RecommendationCacheRepository",
    # Services
    "RecommendationDomainService",
    # Utilities
    "clean_title",
    "extract_artist_from_title",
]
