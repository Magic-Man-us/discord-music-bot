"""AI infrastructure — provider-agnostic via pydantic-ai."""

from .noop_client import NoOpAIClient
from .recommendation_client import AIRecommendationClient

__all__ = ["AIRecommendationClient", "NoOpAIClient"]
