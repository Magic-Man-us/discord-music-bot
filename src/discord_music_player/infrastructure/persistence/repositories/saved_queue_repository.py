"""SQLite repository for saved queue playlists (per-guild, named)."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final

from pydantic import BaseModel, JsonValue, TypeAdapter

from ....domain.music.entities import Track
from ....domain.shared.model_config import FrozenModelConfig
from ....domain.shared.types import (
    DiscordSnowflake,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
)
from ....utils.logging import get_logger

if TYPE_CHECKING:
    from ..database import Database

logger = get_logger(__name__)

_MAX_SAVED_QUEUES_PER_GUILD: int = 25
_TRACK_LIST_ADAPTER: Final = TypeAdapter(list[Track])
_STORED_TRACKS_ADAPTER: Final = TypeAdapter(list[dict[str, JsonValue]])


class _Col(StrEnum):
    ID = "id"
    GUILD_ID = "guild_id"
    NAME = "name"
    TRACKS_JSON = "tracks_json"
    TRACK_COUNT = "track_count"
    CREATED_BY_ID = "created_by_id"
    CREATED_BY_NAME = "created_by_name"
    CREATED_AT = "created_at"


class _TrackField(StrEnum):
    """Track fields persisted into saved queue JSON for later re-resolution."""

    ID = "id"
    TITLE = "title"
    WEBPAGE_URL = "webpage_url"
    DURATION_SECONDS = "duration_seconds"
    ARTIST = "artist"
    UPLOADER = "uploader"


class SavedQueueRow(BaseModel):
    """Boundary between saved_queues DB rows and domain Track lists."""

    model_config = FrozenModelConfig

    _SERIALIZED_FIELDS: ClassVar[set[str]] = {f.value for f in _TrackField}

    id: PositiveInt
    guild_id: DiscordSnowflake
    name: NonEmptyStr
    tracks_json: NonEmptyStr
    track_count: NonNegativeInt
    created_by_id: DiscordSnowflake
    created_by_name: NonEmptyStr
    created_at: NonEmptyStr

    def to_tracks(self) -> list[Track]:
        return _TRACK_LIST_ADAPTER.validate_json(self.tracks_json)

    @staticmethod
    def serialize_tracks(tracks: list[Track]) -> NonEmptyStr:
        projected = [
            track.model_dump(include=SavedQueueRow._SERIALIZED_FIELDS, mode="json")
            for track in tracks
        ]
        return _STORED_TRACKS_ADAPTER.dump_json(projected).decode()

    @classmethod
    def from_db_row(cls, row: dict[str, object]) -> SavedQueueRow:
        return cls.model_validate(row)


class SavedQueueInfo(BaseModel):
    """Summary without track data — used for list display."""

    model_config = FrozenModelConfig

    name: NonEmptyStr
    track_count: NonNegativeInt
    created_by_name: NonEmptyStr
    created_at: NonEmptyStr


class SQLiteSavedQueueRepository:
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(
        self,
        guild_id: DiscordSnowflake,
        name: NonEmptyStr,
        tracks: list[Track],
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
    ) -> bool:
        """Returns False when the per-guild limit is reached and this is a new name."""
        tracks_json = SavedQueueRow.serialize_tracks(tracks)

        async with self._db.transaction() as conn:
            count_row = await (
                await conn.execute(
                    "SELECT COUNT(*) as count FROM saved_queues WHERE guild_id = ?",
                    (guild_id,),
                )
            ).fetchone()
            count = count_row[0] if count_row else 0

            existing_row = await (
                await conn.execute(
                    "SELECT 1 FROM saved_queues WHERE guild_id = ? AND name = ?",
                    (guild_id, name),
                )
            ).fetchone()

            if existing_row is None and count >= _MAX_SAVED_QUEUES_PER_GUILD:
                return False

            insert_params = (guild_id, name, tracks_json, len(tracks), user_id, user_name)
            await conn.execute(
                """
                INSERT INTO saved_queues (guild_id, name, tracks_json, track_count, created_by_id, created_by_name)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, name) DO UPDATE SET
                    tracks_json = excluded.tracks_json,
                    track_count = excluded.track_count,
                    created_by_id = excluded.created_by_id,
                    created_by_name = excluded.created_by_name,
                    created_at = strftime('%Y-%m-%dT%H:%M:%f','now')
                """,
                insert_params,
            )

        logger.info(
            "Saved queue '%s' for guild %s (%d tracks)",
            name,
            guild_id,
            len(tracks),
        )
        return True

    async def get(self, guild_id: DiscordSnowflake, name: NonEmptyStr) -> SavedQueueRow | None:
        row = await self._db.fetch_one(
            "SELECT * FROM saved_queues WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        if row is None:
            return None
        return SavedQueueRow.from_db_row(row)

    async def list_all(self, guild_id: DiscordSnowflake) -> list[SavedQueueInfo]:
        rows = await self._db.fetch_all(
            """
            SELECT name, track_count, created_by_name, created_at
            FROM saved_queues
            WHERE guild_id = ?
            ORDER BY created_at DESC
            """,
            (guild_id,),
        )
        return [SavedQueueInfo.model_validate(row) for row in rows]

    async def delete(self, guild_id: DiscordSnowflake, name: NonEmptyStr) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM saved_queues WHERE guild_id = ? AND name = ?",
            (guild_id, name),
        )
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Deleted saved queue '%s' for guild %s", name, guild_id)
        return deleted

    async def count(self, guild_id: DiscordSnowflake) -> int:
        row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM saved_queues WHERE guild_id = ?",
            (guild_id,),
        )
        return row["count"] if row else 0
