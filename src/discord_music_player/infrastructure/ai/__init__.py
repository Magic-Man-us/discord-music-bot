"""AI infrastructure — provider-agnostic via pydantic-ai."""

from discord_music_player.infrastructure.ai.noop_client import NoOpAIClient
from discord_music_player.infrastructure.ai.recommendation_client import AIRecommendationClient

__all__ = ["AIRecommendationClient", "NoOpAIClient"]
