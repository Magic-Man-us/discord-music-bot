"""SQLite implementation of the session repository."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.repository import SessionRepository
from discord_music_player.domain.music.value_objects import LoopMode, PlaybackState, TrackId
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)


class SQLiteSessionRepository(SessionRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get(self, guild_id: int) -> GuildPlaybackSession | None:
        session_row = await self._db.fetch_one(
            "SELECT * FROM guild_sessions WHERE guild_id = ?",
            (guild_id,),
        )

        if session_row is None:
            return None

        queue_rows = await self._db.fetch_all(
            """
            SELECT * FROM queue_tracks 
            WHERE guild_id = ? 
            ORDER BY position ASC
            """,
            (guild_id,),
        )

        queue: list[Track] = []
        current_track: Track | None = None

        for row in queue_rows:
            track = self._row_to_track(row)
            if row["is_current"]:
                current_track = track
            else:
                queue.append(track)

        return GuildPlaybackSession(
            guild_id=guild_id,
            queue=queue,
            current_track=current_track,
            state=PlaybackState(session_row["state"]),
            loop_mode=LoopMode(session_row["loop_mode"]),
            created_at=UtcDateTime.from_iso(session_row["created_at"]).dt,
            last_activity=UtcDateTime.from_iso(session_row["last_activity"]).dt,
        )

    async def save(self, session: GuildPlaybackSession) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO guild_sessions (guild_id, state, loop_mode, created_at, last_activity)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    state = excluded.state,
                    loop_mode = excluded.loop_mode,
                    last_activity = excluded.last_activity
                """,
                (
                    session.guild_id,
                    session.state.value,
                    session.loop_mode.value,
                    UtcDateTime(session.created_at).iso,
                    UtcDateTime(session.last_activity).iso,
                ),
            )

            await conn.execute(
                "DELETE FROM queue_tracks WHERE guild_id = ?",
                (session.guild_id,),
            )

            if session.current_track:
                await conn.execute(
                    """
                    INSERT INTO queue_tracks (
                        guild_id, track_id, title, webpage_url, stream_url,
                        duration_seconds, thumbnail_url, artist, uploader,
                        like_count, view_count, requested_by_id, requested_by_name,
                        requested_at, position, is_current
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._track_to_params(session.current_track, session.guild_id, -1, True),
                )

            for position, track in enumerate(session.queue):
                await conn.execute(
                    """
                    INSERT INTO queue_tracks (
                        guild_id, track_id, title, webpage_url, stream_url,
                        duration_seconds, thumbnail_url, artist, uploader,
                        like_count, view_count, requested_by_id, requested_by_name,
                        requested_at, position, is_current
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._track_to_params(track, session.guild_id, position, False),
                )

        logger.debug(LogTemplates.SESSION_SAVED, session.guild_id)

    async def delete(self, guild_id: int) -> bool:
        exists = await self.exists(guild_id)
        if not exists:
            return False

        async with self._db.transaction() as conn:
            await conn.execute(
                "DELETE FROM queue_tracks WHERE guild_id = ?",
                (guild_id,),
            )
            await conn.execute(
                "DELETE FROM guild_sessions WHERE guild_id = ?",
                (guild_id,),
            )

        logger.debug(LogTemplates.SESSION_DELETED, guild_id)
        return True

    async def exists(self, guild_id: int) -> bool:
        row = await self._db.fetch_one(
            "SELECT 1 FROM guild_sessions WHERE guild_id = ?",
            (guild_id,),
        )
        return row is not None

    async def get_or_create(self, guild_id: int) -> GuildPlaybackSession:
        session = await self.get(guild_id)
        if session is not None:
            return session

        now = UtcDateTime.now().dt
        session = GuildPlaybackSession(
            guild_id=guild_id,
            queue=[],
            current_track=None,
            state=PlaybackState.IDLE,
            loop_mode=LoopMode.OFF,
            created_at=now,
            last_activity=now,
        )
        await self.save(session)
        return session

    async def get_all_active(self) -> list[GuildPlaybackSession]:
        guild_ids = await self.get_all_guild_ids()
        sessions = []
        for guild_id in guild_ids:
            session = await self.get(guild_id)
            if session is not None:
                sessions.append(session)
        return sessions

    async def get_all_guild_ids(self) -> list[int]:
        rows = await self._db.fetch_all("SELECT guild_id FROM guild_sessions")
        return [row["guild_id"] for row in rows]

    async def count(self) -> int:
        row = await self._db.fetch_one("SELECT COUNT(*) as count FROM guild_sessions")
        return row["count"] if row else 0

    async def cleanup_stale(
        self,
        older_than: datetime | None = None,
        *,
        max_age_hours: int | None = None,
    ) -> int:
        if older_than is None:
            if max_age_hours is None:
                raise TypeError("Either older_than or max_age_hours must be provided")
            cutoff = UtcDateTime.now().dt - timedelta(hours=max_age_hours)
            older_than = cutoff

        count_row = await self._db.fetch_one(
            "SELECT COUNT(*) as count FROM guild_sessions WHERE last_activity < ?",
            (older_than.isoformat(),),
        )
        count = count_row["count"] if count_row else 0

        await self._db.execute(
            "DELETE FROM guild_sessions WHERE last_activity < ?",
            (older_than.isoformat(),),
        )

        if count > 0:
            logger.info("Cleaned up %s stale sessions", count)

        return count

    async def update_activity(self, guild_id: int) -> None:
        await self._db.execute(
            "UPDATE guild_sessions SET last_activity = ? WHERE guild_id = ?",
            (UtcDateTime.now().iso, guild_id),
        )

    def _row_to_track(self, row: dict) -> Track:
        requested_at = None
        if row.get("requested_at"):
            requested_at = UtcDateTime.from_iso(row["requested_at"]).dt

        track_data = {
            "id": TrackId.from_url(row["webpage_url"]),
            "title": row["title"],
            "webpage_url": row["webpage_url"],
            "stream_url": row.get("stream_url"),
            "duration_seconds": row.get("duration_seconds"),
            "thumbnail_url": row.get("thumbnail_url"),
            "artist": row.get("artist"),
            "uploader": row.get("uploader"),
            "like_count": row.get("like_count"),
            "view_count": row.get("view_count"),
            "requested_by_id": row.get("requested_by_id"),
            "requested_by_name": row.get("requested_by_name"),
            "requested_at": requested_at,
        }

        return Track.model_validate(track_data)

    def _track_to_params(
        self, track: Track, guild_id: int, position: int, is_current: bool
    ) -> tuple:
        track_dict = track.model_dump()

        return (
            guild_id,
            track.id.value,
            track_dict["title"],
            track_dict["webpage_url"],
            track_dict["stream_url"],
            track_dict["duration_seconds"],
            track_dict["thumbnail_url"],
            track_dict["artist"],
            track_dict["uploader"],
            track_dict["like_count"],
            track_dict["view_count"],
            track_dict["requested_by_id"],
            track_dict["requested_by_name"],
            UtcDateTime(track.requested_at).iso if track.requested_at else None,
            position,
            is_current,
        )
