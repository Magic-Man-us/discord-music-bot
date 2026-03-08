"""SQLite implementation of the session repository."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.repository import SessionRepository
from discord_music_player.domain.music.enums import LoopMode, PlaybackState
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.infrastructure.persistence.models import QUEUE_TRACKS_INSERT_SQL, QueueTrackRow, TrackRow

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

        for raw_row in queue_rows:
            row = TrackRow.model_validate(raw_row)
            track = row.to_track(id_from_url=True)
            if raw_row["is_current"]:
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
                row = QueueTrackRow.from_track(
                    session.current_track, guild_id=session.guild_id, position=-1, is_current=True,
                )
                await conn.execute(QUEUE_TRACKS_INSERT_SQL, row.model_dump())

            for position, track in enumerate(session.queue):
                row = QueueTrackRow.from_track(
                    track, guild_id=session.guild_id, position=position, is_current=False,
                )
                await conn.execute(QUEUE_TRACKS_INSERT_SQL, row.model_dump())

        logger.debug("Saved session for guild %s", session.guild_id)

    async def delete(self, guild_id: int) -> bool:
        async with self._db.transaction() as conn:
            await conn.execute(
                "DELETE FROM queue_tracks WHERE guild_id = ?",
                (guild_id,),
            )
            cursor = await conn.execute(
                "DELETE FROM guild_sessions WHERE guild_id = ?",
                (guild_id,),
            )
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug("Deleted session for guild %s", guild_id)
        return deleted

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
