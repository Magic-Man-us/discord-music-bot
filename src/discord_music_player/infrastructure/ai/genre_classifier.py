"""AI-powered genre classifier for track analytics, using pydantic-ai."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from discord_music_player.config.settings import AISettings

logger = logging.getLogger(__name__)

GENRE_VOCABULARY = [
    "Rock", "Pop", "Hip-Hop", "Electronic", "R&B", "Country", "Jazz",
    "Classical", "Latin", "Metal", "Folk", "Indie", "Reggae", "Blues",
    "Punk", "Soul", "Funk", "Ambient", "Other",
]

BATCH_SIZE = 20


class GenreClassificationResponse(BaseModel):
    genres: dict[str, str] = Field(default_factory=dict)


class AIGenreClassifier:
    def __init__(self, settings: AISettings) -> None:
        self._settings = settings
        self._agent: Agent[None, GenreClassificationResponse] | None = None

    def is_available(self) -> bool:
        try:
            self._get_agent()
            return True
        except Exception:
            return False

    def _get_agent(self) -> Agent[None, GenreClassificationResponse]:
        if self._agent is not None:
            return self._agent

        genres_text = ", ".join(GENRE_VOCABULARY)
        system_prompt = (
            "You are a music genre classifier. "
            f"Allowed genres: {genres_text}. "
            "Rules:\n"
            "- Classify each track into exactly one genre from the allowed list.\n"
            "- Use the track title and artist to determine genre.\n"
            "- If unsure, use 'Other'.\n"
        )

        self._agent = Agent(
            self._settings.model,
            output_type=GenreClassificationResponse,
            system_prompt=system_prompt,
        )
        return self._agent

    async def classify_tracks(
        self, tracks: list[tuple[str, str | None]]
    ) -> dict[str, str]:
        """Classify tracks by genre using AI.

        Args:
            tracks: List of (track_id, "title - artist" or just "title") tuples.

        Returns:
            Dict mapping track_id -> genre string.
        """
        if not tracks:
            return {}

        results: dict[str, str] = {}

        for i in range(0, len(tracks), BATCH_SIZE):
            batch = tracks[i : i + BATCH_SIZE]
            batch_results = await self._classify_batch(batch)
            results.update(batch_results)

        return results

    async def _classify_batch(
        self, batch: list[tuple[str, str | None]]
    ) -> dict[str, str]:
        try:
            agent = self._get_agent()

            track_lines = []
            for track_id, description in batch:
                track_lines.append(f"- id:{track_id} | {description or 'Unknown'}")

            tracks_text = "\n".join(track_lines)
            user_prompt = f"Classify these tracks:\n{tracks_text}"

            ai_result = await agent.run(
                user_prompt,
                model_settings={
                    "max_tokens": self._settings.max_tokens,
                    "temperature": 0.3,
                },
            )

            genres = ai_result.output.genres

            result = {}
            for track_id, _ in batch:
                genre = genres.get(track_id, "Unknown")
                if genre not in GENRE_VOCABULARY:
                    genre = "Other"
                result[track_id] = genre

            logger.info(LogTemplates.ANALYTICS_GENRE_CLASSIFIED, len(result))
            return result

        except Exception as e:
            logger.error(LogTemplates.ANALYTICS_GENRE_CLASSIFICATION_FAILED, e)
            return {tid: "Unknown" for tid, _ in batch}
