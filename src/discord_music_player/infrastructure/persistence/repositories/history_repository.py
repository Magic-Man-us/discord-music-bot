"""SQLite implementation of the track history repository."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.repository import TrackHistoryRepository
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)


class SQLiteHistoryRepository(TrackHistoryRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def record_play(
        self, guild_id: int, track: Track, played_at: datetime | None = None
    ) -> None:
        if played_at is None:
            played_at = UtcDateTime.now().dt

        track_dict = track.model_dump()

        await self._db.execute(
            """
            INSERT INTO track_history (
                guild_id, track_id, title, webpage_url, duration_seconds,
                artist, uploader, like_count, view_count,
                requested_by_id, requested_by_name, played_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                track.id.value,
                track_dict["title"],
                track_dict["webpage_url"],
                track_dict["duration_seconds"],
                track_dict["artist"],
                track_dict["uploader"],
                track_dict["like_count"],
                track_dict["view_count"],
                track_dict["requested_by_id"],
                track_dict["requested_by_name"],
                UtcDateTime(played_at).iso,
            ),
        )
        logger.debug(
            LogTemplates.HISTORY_RECORDED,
            track.title,
            guild_id,
        )

    async def get_guild_history(self, guild_id: int, limit: int = 10) -> list[Any]:
        from dataclasses import dataclass

        @dataclass
        class _HistoryItem:
            track: Track

        tracks = await self.get_recent(guild_id, limit=limit)
        return [_HistoryItem(track=t) for t in tracks]

    async def get_recent_titles(self, guild_id: int, limit: int = 10) -> list[str]:
        tracks = await self.get_recent(guild_id, limit=limit)
        return [t.title for t in tracks]

    async def cleanup_old(
        self,
        older_than: datetime | None = None,
        *,
        max_age_days: int | None = None,
    ) -> int:
        if older_than is None:
            if max_age_days is None:
                raise TypeError("Either older_than or max_age_days must be provided")
            older_than = UtcDateTime.now().dt - timedelta(days=max_age_days)

        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM track_history WHERE played_at < ?",
            (older_than.isoformat(),),
        )
        count = count_row["count"] if count_row else 0

        await self._db.execute(
            "DELETE FROM track_history WHERE played_at < ?",
            (older_than.isoformat(),),
        )

        if count > 0:
            logger.info(LogTemplates.HISTORY_OLD_CLEANED, count)

        return count

    async def get_recent(self, guild_id: int, limit: int = 10) -> list[Track]:
        rows = await self._db.fetch_all(
            """
            SELECT * FROM track_history
            WHERE guild_id = ?
            ORDER BY played_at DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return [self._row_to_track(row) for row in rows]

    async def get_play_count(self, guild_id: int, track_id: TrackId) -> int:
        row = await self._db.fetch_one(
            """
            SELECT COUNT(*) as count FROM track_history
            WHERE guild_id = ? AND track_id = ?
            """,
            (guild_id, track_id.value),
        )
        return row["count"] if row else 0

    async def get_most_played(self, guild_id: int, limit: int = 10) -> list[tuple[Track, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT *, COUNT(*) as play_count
            FROM track_history
            WHERE guild_id = ?
            GROUP BY track_id
            ORDER BY play_count DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return [(self._row_to_track(row), row["play_count"]) for row in rows]

    async def clear_history(self, guild_id: int) -> int:
        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )
        count = count_row["count"] if count_row else 0

        await self._db.execute(
            "DELETE FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )

        logger.info(LogTemplates.HISTORY_CLEARED, count, guild_id)
        return count

    async def mark_finished(self, guild_id: int, track_id: TrackId, skipped: bool = False) -> None:
        await self._db.execute(
            """
            UPDATE track_history
            SET finished_at = ?, skipped = ?
            WHERE id = (
                SELECT id FROM track_history
                WHERE guild_id = ? AND track_id = ?
                ORDER BY played_at DESC
                LIMIT 1
            )
            """,
            (UtcDateTime.now().iso, skipped, guild_id, track_id.value),
        )

    def _row_to_track(self, row: dict) -> Track:
        requested_at = None
        if row.get("requested_at"):
            requested_at = UtcDateTime.from_iso(row["requested_at"]).dt

        track_data = {
            "id": TrackId(row["track_id"]),
            "title": row["title"],
            "webpage_url": row["webpage_url"],
            "stream_url": None,
            "duration_seconds": row.get("duration_seconds"),
            "thumbnail_url": None,
            "artist": row.get("artist"),
            "uploader": row.get("uploader"),
            "like_count": row.get("like_count"),
            "view_count": row.get("view_count"),
            "requested_by_id": row.get("requested_by_id"),
            "requested_by_name": row.get("requested_by_name"),
            "requested_at": requested_at,
        }

        return Track.model_validate(track_data)
