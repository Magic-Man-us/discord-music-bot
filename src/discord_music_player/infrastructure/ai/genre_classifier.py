"""AI-powered genre classifier for track analytics, using pydantic-ai."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from discord_music_player.domain.shared.types import TrackForClassification, TrackGenreMap

if TYPE_CHECKING:
    from discord_music_player.config.settings import AISettings

_BATCH_SIZE = 20
_UNKNOWN_GENRE = "Unknown"


class GenreClassificationResponse(BaseModel):
    """AI agent output mapping track IDs to genre strings."""

    model_config = ConfigDict(frozen=True)

    genres: TrackGenreMap = Field(default_factory=dict)


class AIGenreClassifier:
    """Classifies tracks into genres via an AI agent (genres are AI-determined, not hardcoded)."""

    def __init__(self, settings: AISettings) -> None:
        self._settings = settings
        self._agent: Agent[None, GenreClassificationResponse] | None = None
        self._logger = logging.getLogger(type(self).__module__)

    def is_available(self) -> bool:
        try:
            self._get_agent()
            return True
        except Exception:
            return False

    def _get_agent(self) -> Agent[None, GenreClassificationResponse]:
        if self._agent is not None:
            return self._agent

        system_prompt = (
            "You are a music genre classifier. "
            "Rules:\n"
            "- Classify each track into exactly one genre.\n"
            "- Use the track title and artist to determine genre.\n"
            "- Use standard, widely-recognised genre names (e.g. Rock, Pop, Hip-Hop, Electronic, Jazz, Classical, R&B, Metal, Folk, Country).\n"
            "- Keep genre names short (one or two words) and consistent across tracks.\n"
            "- If the genre is genuinely unclear, use 'Other'.\n"
        )

        self._agent = Agent(
            self._settings.model,
            output_type=GenreClassificationResponse,
            system_prompt=system_prompt,
        )
        return self._agent

    async def classify_tracks(
        self, tracks: list[TrackForClassification]
    ) -> TrackGenreMap:
        """Batch-classify tracks into genres, splitting into chunks of _BATCH_SIZE."""
        if not tracks:
            return {}

        results: TrackGenreMap = {}

        for i in range(0, len(tracks), _BATCH_SIZE):
            batch = tracks[i : i + _BATCH_SIZE]
            batch_results = await self._classify_batch(batch)
            results.update(batch_results)

        return results

    async def _classify_batch(
        self, batch: list[TrackForClassification]
    ) -> TrackGenreMap:
        try:
            agent = self._get_agent()

            track_lines = [
                f"- id:{t.track_id} | {t.description or _UNKNOWN_GENRE}"
                for t in batch
            ]

            user_prompt = f"Classify these tracks:\n{chr(10).join(track_lines)}"

            settings = ModelSettings(
                max_tokens=self._settings.max_tokens,
                temperature=self._settings.temperature,
            )
            ai_result = await agent.run(user_prompt, model_settings=settings)

            genres = ai_result.output.genres

            result: TrackGenreMap = {
                t.track_id: genres.get(t.track_id, _UNKNOWN_GENRE)
                for t in batch
            }

            self._logger.info("Classified %d tracks into genres", len(result))
            return result

        except Exception as e:
            self._logger.error("Genre classification failed: %s", e)
            return {t.track_id: _UNKNOWN_GENRE for t in batch}
