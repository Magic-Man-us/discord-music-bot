"""SQLite cache repository for AI genre classifications."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord_music_player.domain.shared.datetime_utils import UtcDateTime

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)


class SQLiteGenreCacheRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_genres(self, track_ids: list[str]) -> dict[str, str]:
        """Batch lookup cached genre classifications."""
        if not track_ids:
            return {}

        placeholders = ",".join("?" for _ in track_ids)
        rows = await self._db.fetch_all(
            f"SELECT track_id, genre FROM track_genres WHERE track_id IN ({placeholders})",  # noqa: S608
            tuple(track_ids),
        )
        return {row["track_id"]: row["genre"] for row in rows}

    async def save_genres(self, classifications: dict[str, str]) -> None:
        """Batch upsert genre classifications."""
        if not classifications:
            return

        now = UtcDateTime.now().iso
        for track_id, genre in classifications.items():
            await self._db.execute(
                """
                INSERT INTO track_genres (track_id, genre, classified_at)
                VALUES (?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET genre = ?, classified_at = ?
                """,
                (track_id, genre, now, genre, now),
            )
