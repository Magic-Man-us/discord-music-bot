"""AI infrastructure.

Only the OpenAI client is implemented. A previous re-export of `SingleFlight`
was removed because the module no longer exists.
"""

from discord_music_player.infrastructure.ai.openai_client import OpenAIRecommendationClient

__all__ = ["OpenAIRecommendationClient"]
