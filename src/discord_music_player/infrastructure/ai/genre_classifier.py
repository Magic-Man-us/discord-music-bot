"""OpenAI-based genre classifier for track analytics."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

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


class OpenAIGenreClassifier:
    def __init__(self, settings: AISettings) -> None:
        self._settings = settings
        self._client: AsyncOpenAI | None = None

    def is_available(self) -> bool:
        return bool(self._settings.api_key.get_secret_value())

    def _get_client(self) -> AsyncOpenAI:
        if self._client is not None:
            return self._client

        api_key_value = self._settings.api_key.get_secret_value()
        if not api_key_value:
            msg = "OPENAI_API_KEY is not set"
            raise RuntimeError(msg)

        self._client = AsyncOpenAI(api_key=api_key_value, max_retries=0)
        return self._client

    async def classify_tracks(
        self, tracks: list[tuple[str, str | None]]
    ) -> dict[str, str]:
        """Classify tracks by genre using OpenAI.

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
            client = self._get_client()

            track_lines = []
            for track_id, description in batch:
                track_lines.append(f"- id:{track_id} | {description or 'Unknown'}")

            tracks_text = "\n".join(track_lines)
            genres_text = ", ".join(GENRE_VOCABULARY)

            system = (
                "You are a music genre classifier. Respond with STRICT JSON (no markdown). "
                f"Allowed genres: {genres_text}. "
                'Schema: {{"genres": {{"<track_id>": "<genre>", ...}}}}. '
                "Rules:\n"
                "- Classify each track into exactly one genre from the allowed list.\n"
                "- Use the track title and artist to determine genre.\n"
                "- If unsure, use 'Other'.\n"
                "- No extra text outside the JSON object."
            )

            user = f"Classify these tracks:\n{tracks_text}"

            response = await client.with_options(timeout=20.0).chat.completions.create(
                model=self._settings.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=self._settings.max_tokens,
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return {tid: "Unknown" for tid, _ in batch}

            data = json.loads(content)
            genres = data.get("genres", {})

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
