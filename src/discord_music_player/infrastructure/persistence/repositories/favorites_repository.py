"""SQLite implementation of the user favorites repository."""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.domain.shared.types import (
    DiscordSnowflake,
    DurationSeconds,
    HttpUrlStr,
    NonEmptyStr,
    PositiveInt,
)

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)

_MAX_FAVORITES = 100

class _Col(StrEnum):
    TRACK_ID = "track_id"
    TITLE = "title"
    WEBPAGE_URL = "webpage_url"
    DURATION_SECONDS = "duration_seconds"
    ARTIST = "artist"
    UPLOADER = "uploader"


class FavoriteRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    track_id: NonEmptyStr
    title: NonEmptyStr
    webpage_url: HttpUrlStr
    duration_seconds: DurationSeconds | None = None
    artist: NonEmptyStr | None = None
    uploader: NonEmptyStr | None = None

    def to_track(self) -> Track:
        data = self.model_dump()
        data["id"] = TrackId(value=data.pop("track_id"))
        return Track.model_validate(data)

    # Fields shared between FavoriteRow and Track (used for model_dump projection)
    _TRACK_FIELDS: ClassVar[set[str]] = {
        _Col.TITLE, _Col.WEBPAGE_URL, _Col.DURATION_SECONDS, _Col.ARTIST, _Col.UPLOADER,
    }

    @classmethod
    def from_track(cls, track: Track) -> FavoriteRow:
        track_id_str = track.id.value if isinstance(track.id, TrackId) else str(track.id)
        dump = track.model_dump(include=cls._TRACK_FIELDS)
        dump[_Col.TRACK_ID] = track_id_str
        return cls.model_validate(dump)

    @classmethod
    def from_db_row(cls, row: tuple[str, ...]) -> FavoriteRow:
        return cls.model_validate(dict(zip(_Col, row, strict=False)))


class SQLiteFavoritesRepository:

    def __init__(self, database: Database) -> None:
        self._db = database

    async def add(self, user_id: DiscordSnowflake, track: Track) -> bool:
        async with self._db.connection() as conn:
            row = await conn.execute_fetchall(
                "SELECT COUNT(*) as count FROM user_favorites WHERE user_id = :user_id",
                {"user_id": user_id},
            )
            if row and row[0][0] >= _MAX_FAVORITES:
                return False

            try:
                fav = FavoriteRow.from_track(track)
                params = {"user_id": user_id, **fav.model_dump()}
                await conn.execute(
                    """
                    INSERT OR IGNORE INTO user_favorites
                        (user_id, track_id, title, webpage_url, duration_seconds, artist, uploader)
                    VALUES
                        (:user_id, :track_id, :title, :webpage_url, :duration_seconds, :artist, :uploader)
                    """,
                    params,
                )
                await conn.commit()
                return True
            except Exception:
                logger.exception("Failed to add favorite for user %s", user_id)
                return False

    async def remove(self, user_id: DiscordSnowflake, track_id: str) -> bool:
        async with self._db.connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM user_favorites WHERE user_id = :user_id AND track_id = :track_id",
                {"user_id": user_id, "track_id": track_id},
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def get_all(
        self, user_id: DiscordSnowflake, limit: PositiveInt = 50
    ) -> list[Track]:
        async with self._db.connection() as conn:
            rows = await conn.execute_fetchall(
                """
                SELECT track_id, title, webpage_url, duration_seconds, artist, uploader
                FROM user_favorites
                WHERE user_id = :user_id
                ORDER BY added_at DESC
                LIMIT :limit
                """,
                {"user_id": user_id, "limit": limit},
            )

        return [FavoriteRow.from_db_row(row).to_track() for row in rows]

    async def is_favorited(self, user_id: DiscordSnowflake, track_id: str) -> bool:
        async with self._db.connection() as conn:
            rows = await conn.execute_fetchall(
                "SELECT 1 FROM user_favorites WHERE user_id = :user_id AND track_id = :track_id",
                {"user_id": user_id, "track_id": track_id},
            )
            return len(rows) > 0

    async def count(self, user_id: DiscordSnowflake) -> int:
        async with self._db.connection() as conn:
            rows = await conn.execute_fetchall(
                "SELECT COUNT(*) FROM user_favorites WHERE user_id = :user_id",
                {"user_id": user_id},
            )
            return rows[0][0] if rows else 0
