"""SQLite implementation of the recommendation cache repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from ....domain.recommendations.entities import (
    CacheStats,
    Recommendation,
    RecommendationSet,
)
from ....domain.recommendations.repository import RecommendationCacheRepository
from ....domain.shared.datetime_utils import UtcDateTime
from ....utils.logging import get_logger

if TYPE_CHECKING:
    from ..database import Database

logger = get_logger(__name__)

_recommendation_list_ta = TypeAdapter(list[Recommendation])

_COUNT_COL = "count"


class SQLiteCacheRepository(RecommendationCacheRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get(self, cache_key: str) -> RecommendationSet | None:
        now_iso = UtcDateTime.now().iso

        row = await self._db.fetch_one(
            """
            SELECT * FROM recommendation_cache
            WHERE cache_key = ? AND expires_at > ?
            """,
            (cache_key, now_iso),
        )

        if row is None:
            return None

        try:
            recommendations = _recommendation_list_ta.validate_json(row["recommendations_json"])

            expires_at = None
            if row.get("expires_at"):
                expires_at = UtcDateTime.from_iso(row["expires_at"]).dt

            return RecommendationSet(
                base_track_title=row["base_track_title"],
                base_track_artist=row.get("base_track_artist"),
                recommendations=recommendations,
                generated_at=UtcDateTime.from_iso(row["generated_at"]).dt,
                expires_at=expires_at,
            )
        except (ValueError, KeyError) as e:
            logger.warning("Failed to parse cached recommendations: %s", e)
            return None

    async def save(self, recommendation_set: RecommendationSet) -> None:
        cache_key = recommendation_set.cache_key

        recommendations_json = _recommendation_list_ta.dump_json(
            recommendation_set.recommendations
        ).decode()

        await self._db.execute(
            """
            INSERT INTO recommendation_cache (
                cache_key, base_track_id, base_track_title,
                base_track_artist, recommendations_json, generated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                base_track_title = excluded.base_track_title,
                base_track_artist = excluded.base_track_artist,
                recommendations_json = excluded.recommendations_json,
                generated_at = excluded.generated_at,
                expires_at = excluded.expires_at
            """,
            (
                cache_key,
                cache_key,
                recommendation_set.base_track_title,
                recommendation_set.base_track_artist,
                recommendations_json,
                UtcDateTime(recommendation_set.generated_at).iso,
                UtcDateTime(recommendation_set.expires_at).iso
                if recommendation_set.expires_at
                else None,
            ),
        )

    async def delete(self, cache_key: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM recommendation_cache WHERE cache_key = ?",
            (cache_key,),
        )
        return cursor.rowcount > 0

    async def clear(self) -> int:
        cursor = await self._db.execute("DELETE FROM recommendation_cache")
        return cursor.rowcount

    async def cleanup_expired(self) -> int:
        now_iso = UtcDateTime.now().iso
        cursor = await self._db.execute(
            "DELETE FROM recommendation_cache WHERE expires_at < ?",
            (now_iso,),
        )
        return cursor.rowcount

    async def prune(self, max_entries: int) -> int:
        count = await self.count()
        if count <= max_entries:
            return 0

        entries_to_prune = count - max_entries
        cursor = await self._db.execute(
            """
            DELETE FROM recommendation_cache
            WHERE id IN (
                SELECT id FROM recommendation_cache
                ORDER BY generated_at ASC
                LIMIT ?
            )
            """,
            (entries_to_prune,),
        )
        return cursor.rowcount

    async def count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) as count FROM recommendation_cache")
        return row[_COUNT_COL] if row else 0

    async def get_stats(self) -> CacheStats:
        now = UtcDateTime.now().iso
        row = await self._db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                COALESCE(SUM(CASE WHEN expires_at < ? THEN 1 ELSE 0 END), 0) as expired,
                MIN(generated_at) as oldest,
                MAX(generated_at) as newest
            FROM recommendation_cache
            """,
            (now,),
        )
        if not row or row["total"] == 0:
            return CacheStats()

        total: int = row["total"]
        expired: int = row["expired"]
        oldest = UtcDateTime.from_iso(row["oldest"]).dt if row.get("oldest") else None
        newest = UtcDateTime.from_iso(row["newest"]).dt if row.get("newest") else None

        return CacheStats(
            total_entries=total,
            expired_entries=expired,
            valid_entries=total - expired,
            oldest_entry=oldest,
            newest_entry=newest,
        )
