"""SQLite implementation of the track history repository."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.repository import TrackHistoryRepository
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.types import NonEmptyStr, NonNegativeInt, UnitInterval
from discord_music_player.infrastructure.persistence.models import TrackRow

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)


# SQL result-set column aliases used across multiple analytics queries.
_COUNT: str = "count"
_TOTAL: str = "total"
_TITLE: str = "title"
_TOTAL_TRACKS: str = "total_tracks"


class UserStats(BaseModel):
    """Per-user listening statistics for a guild."""

    model_config = ConfigDict(frozen=True)

    total_tracks: NonNegativeInt = 0
    unique_tracks: NonNegativeInt = 0
    total_listen_time: NonNegativeInt = 0
    skip_rate: UnitInterval = 0.0


class GenreTrackInfo(BaseModel):
    """Minimal track metadata used for genre classification."""

    model_config = ConfigDict(frozen=True)

    track_id: NonEmptyStr
    title: NonEmptyStr
    artist: NonEmptyStr | None = None


class SQLiteHistoryRepository(TrackHistoryRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def record_play(
        self, guild_id: int, track: Track, played_at: datetime | None = None
    ) -> None:
        if played_at is None:
            played_at = UtcDateTime.now().dt

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
                track.title,
                track.webpage_url,
                track.duration_seconds,
                track.artist,
                track.uploader,
                track.like_count,
                track.view_count,
                track.requested_by_id,
                track.requested_by_name,
                UtcDateTime(played_at).iso,
            ),
        )
        logger.debug(
            "Recorded play for track %s in guild %s",
            track.title,
            guild_id,
        )

    async def get_guild_history(self, guild_id: int, limit: int = 10) -> list[Track]:
        return await self.get_recent(guild_id, limit=limit)

    async def get_recent_titles(self, guild_id: int, limit: int = 10) -> list[str]:
        rows = await self._db.fetch_all(
            "SELECT title FROM track_history WHERE guild_id = ? ORDER BY played_at DESC LIMIT ?",
            (guild_id, limit),
        )
        return [row[_TITLE] for row in rows]

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
        count = count_row[_COUNT] if count_row else 0

        await self._db.execute(
            "DELETE FROM track_history WHERE played_at < ?",
            (older_than.isoformat(),),
        )

        if count > 0:
            logger.info("Cleaned up %s old history entries", count)

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
        return [TrackRow.model_validate(row).to_track() for row in rows]

    async def get_play_count(self, guild_id: int, track_id: TrackId) -> int:
        row = await self._db.fetch_one(
            """
            SELECT COUNT(*) as count FROM track_history
            WHERE guild_id = ? AND track_id = ?
            """,
            (guild_id, track_id.value),
        )
        return row[_COUNT] if row else 0

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
        return [(TrackRow.model_validate(row).to_track(), row["play_count"]) for row in rows]

    async def clear_history(self, guild_id: int) -> int:
        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )
        count = count_row[_COUNT] if count_row else 0

        await self._db.execute(
            "DELETE FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )

        logger.info("Cleared %s history entries for guild %s", count, guild_id)
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

    # === Analytics Methods ===

    async def get_total_tracks(self, guild_id: int) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )
        return row[_COUNT] if row else 0

    async def get_unique_tracks(self, guild_id: int) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(DISTINCT track_id) as count FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )
        return row[_COUNT] if row else 0

    async def get_total_listen_time(self, guild_id: int) -> int:
        row = await self._db.fetch_one(
            "SELECT COALESCE(SUM(duration_seconds), 0) as total FROM track_history WHERE guild_id = ?",
            (guild_id,),
        )
        return row[_TOTAL] if row else 0

    async def get_top_requesters(
        self, guild_id: int, limit: int = 10
    ) -> list[tuple[int, str, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT requested_by_id, requested_by_name, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ? AND requested_by_id IS NOT NULL
            GROUP BY requested_by_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return [
            (row["requested_by_id"], row["requested_by_name"] or "Unknown", row[_COUNT])
            for row in rows
        ]

    async def get_skip_rate(self, guild_id: int) -> float:
        row = await self._db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(skipped), 0) as skipped
            FROM track_history
            WHERE guild_id = ?
            """,
            (guild_id,),
        )
        if not row or row[_TOTAL] == 0:
            return 0.0
        return row["skipped"] / row[_TOTAL]

    async def get_most_skipped(self, guild_id: int, limit: int = 10) -> list[tuple[str, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT title, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ? AND skipped = 1
            GROUP BY track_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (guild_id, limit),
        )
        return [(row[_TITLE], row[_COUNT]) for row in rows]

    async def get_user_stats(self, guild_id: int, user_id: int) -> UserStats:
        row = await self._db.fetch_one(
            """
            SELECT
                COUNT(*) as total_tracks,
                COUNT(DISTINCT track_id) as unique_tracks,
                COALESCE(SUM(duration_seconds), 0) as total_listen_time,
                COALESCE(SUM(skipped), 0) as skipped_count
            FROM track_history
            WHERE guild_id = ? AND requested_by_id = ?
            """,
            (guild_id, user_id),
        )
        if not row or row[_TOTAL_TRACKS] == 0:
            return UserStats()

        return UserStats(
            total_tracks=row[_TOTAL_TRACKS],
            unique_tracks=row["unique_tracks"],
            total_listen_time=row["total_listen_time"],
            skip_rate=row["skipped_count"] / row[_TOTAL_TRACKS],
        )

    async def get_user_top_tracks(
        self, guild_id: int, user_id: int, limit: int = 10
    ) -> list[tuple[str, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT title, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ? AND requested_by_id = ?
            GROUP BY track_id
            ORDER BY count DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        )
        return [(row[_TITLE], row[_COUNT]) for row in rows]

    async def get_activity_by_day(self, guild_id: int, days: int = 30) -> list[tuple[str, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT DATE(played_at) as day, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ? AND played_at >= DATE('now', ?)
            GROUP BY day
            ORDER BY day ASC
            """,
            (guild_id, f"-{days} days"),
        )
        return [(row["day"], row[_COUNT]) for row in rows]

    async def get_activity_by_hour(self, guild_id: int) -> list[tuple[int, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT CAST(strftime('%H', played_at) AS INTEGER) as hour, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ?
            GROUP BY hour
            ORDER BY hour ASC
            """,
            (guild_id,),
        )
        return [(row["hour"], row[_COUNT]) for row in rows]

    async def get_activity_by_weekday(self, guild_id: int) -> list[tuple[int, int]]:
        rows = await self._db.fetch_all(
            """
            SELECT CAST(strftime('%w', played_at) AS INTEGER) as weekday, COUNT(*) as count
            FROM track_history
            WHERE guild_id = ?
            GROUP BY weekday
            ORDER BY weekday ASC
            """,
            (guild_id,),
        )
        return [(row["weekday"], row[_COUNT]) for row in rows]

    async def get_user_tracks_for_genre(
        self, guild_id: int, user_id: int
    ) -> list[GenreTrackInfo]:
        rows = await self._db.fetch_all(
            """
            SELECT track_id, title, artist
            FROM track_history
            WHERE guild_id = ? AND requested_by_id = ?
            """,
            (guild_id, user_id),
        )
        return [
            GenreTrackInfo(
                track_id=row["track_id"],
                title=row[_TITLE],
                artist=row.get("artist"),
            )
            for row in rows
        ]
