"""SQLite implementation of the vote session repository."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.datetime_utils import UtcDateTime
from discord_music_player.domain.shared.messages import LogTemplates
from discord_music_player.domain.voting.entities import VoteSession
from discord_music_player.domain.voting.repository import VoteSessionRepository
from discord_music_player.domain.voting.value_objects import VoteType

if TYPE_CHECKING:
    from ..database import Database

logger = logging.getLogger(__name__)


class SQLiteVoteSessionRepository(VoteSessionRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def get_active(self, guild_id: int, track_id: TrackId) -> VoteSession | None:
        session = await self.get(guild_id=guild_id, vote_type=VoteType.SKIP)
        if session is None:
            return None
        return session if session.track_id == track_id else None

    async def delete_by_track(self, guild_id: int, track_id: TrackId) -> bool:
        session = await self.get_active(guild_id, track_id)
        if session is None:
            return False
        return await self.delete(guild_id, session.vote_type)

    async def get(self, guild_id: int, vote_type: VoteType) -> VoteSession | None:
        row = await self._db.fetch_one(
            """
            SELECT * FROM vote_sessions
            WHERE guild_id = ? AND vote_type = ?
            AND completed_at IS NULL
            """,
            (guild_id, vote_type.value),
        )

        if row is None:
            return None

        votes_rows = await self._db.fetch_all(
            "SELECT user_id FROM votes WHERE vote_session_id = ?",
            (row["id"],),
        )
        voters = {vr["user_id"] for vr in votes_rows}

        session = VoteSession(
            guild_id=guild_id,
            track_id=TrackId(row["track_id"]),
            vote_type=VoteType(row["vote_type"]),
            threshold=row["threshold"],
            started_at=UtcDateTime.from_iso(row["started_at"]).dt,
            _voters=voters,
        )

        if session.is_expired:
            await self.delete(guild_id, session.vote_type)
            return None
        return session

    async def get_or_create(
        self,
        guild_id: int,
        track_id: TrackId,
        vote_type: VoteType,
        threshold: int,
    ) -> VoteSession:
        existing = await self.get(guild_id, vote_type)

        if existing is not None:
            if existing.track_id != track_id:
                await self.delete(guild_id, vote_type)
            else:
                if existing.threshold != threshold:
                    existing.update_threshold(threshold)
                    await self.save(existing)
                return existing

        now = UtcDateTime.now().dt
        session = VoteSession(
            guild_id=guild_id,
            track_id=track_id,
            vote_type=vote_type,
            threshold=threshold,
            started_at=now,
        )
        await self.save(session)
        return session

    async def save(self, session: VoteSession) -> None:
        async with self._db.transaction() as conn:
            existing_row = await conn.execute(
                """
                SELECT id FROM vote_sessions
                WHERE guild_id = ? AND vote_type = ?
                AND completed_at IS NULL
                """,
                (session.guild_id, session.vote_type.value),
            )
            existing = await existing_row.fetchone()

            if existing:
                session_id = existing["id"]
                await conn.execute(
                    """
                    UPDATE vote_sessions
                    SET track_id = ?, threshold = ?, started_at = ?
                    WHERE id = ?
                    """,
                    (
                        session.track_id.value,
                        session.threshold,
                        UtcDateTime(session.started_at).iso,
                        session_id,
                    ),
                )
                await conn.execute(
                    "DELETE FROM votes WHERE vote_session_id = ?",
                    (session_id,),
                )
            else:
                cursor = await conn.execute(
                    """
                    INSERT INTO vote_sessions (guild_id, track_id, vote_type, threshold, started_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session.guild_id,
                        session.track_id.value,
                        session.vote_type.value,
                        session.threshold,
                        UtcDateTime(session.started_at).iso,
                    ),
                )
                session_id = cursor.lastrowid

            for user_id in session._voters:
                await conn.execute(
                    "INSERT OR IGNORE INTO votes (vote_session_id, user_id) VALUES (?, ?)",
                    (session_id, user_id),
                )

        logger.debug(LogTemplates.VOTE_SESSION_SAVED, session.guild_id)

    async def delete(self, guild_id: int, vote_type: VoteType) -> bool:
        row = await self._db.fetch_one(
            """
            SELECT id FROM vote_sessions
            WHERE guild_id = ? AND vote_type = ?
            AND completed_at IS NULL
            """,
            (guild_id, vote_type.value),
        )

        if row is None:
            return False

        async with self._db.transaction() as conn:
            await conn.execute(
                "DELETE FROM votes WHERE vote_session_id = ?",
                (row["id"],),
            )
            await conn.execute(
                """
                DELETE FROM vote_sessions
                WHERE guild_id = ? AND vote_type = ?
                AND completed_at IS NULL
                """,
                (guild_id, vote_type.value),
            )

        logger.debug(LogTemplates.VOTE_SESSION_DELETED, guild_id)
        return True

    async def delete_for_guild(self, guild_id: int) -> int:
        count_row = await self._db.fetch_one(
            """
            SELECT COUNT(*) as count FROM vote_sessions
            WHERE guild_id = ? AND completed_at IS NULL
            """,
            (guild_id,),
        )
        count = count_row["count"] if count_row else 0

        await self._db.execute(
            """
            DELETE FROM vote_sessions
            WHERE guild_id = ? AND completed_at IS NULL
            """,
            (guild_id,),
        )

        logger.debug(LogTemplates.VOTE_SESSIONS_DELETED, count, guild_id)
        return count

    async def cleanup_expired(self) -> int:
        now = UtcDateTime.now().dt
        expiration_minutes = VoteSession.DEFAULT_EXPIRATION_MINUTES

        count_row = await self._db.fetch_one(
            f"""
            SELECT COUNT(*) as count FROM vote_sessions
            WHERE completed_at IS NULL
            AND datetime(started_at, '+{expiration_minutes} minutes') < datetime(?)
            """,
            (UtcDateTime(now).iso,),
        )
        count = count_row["count"] if count_row else 0

        await self._db.execute(
            f"""
            DELETE FROM vote_sessions
            WHERE completed_at IS NULL
            AND datetime(started_at, '+{expiration_minutes} minutes') < datetime(?)
            """,
            (UtcDateTime(now).iso,),
        )

        if count > 0:
            logger.info(LogTemplates.VOTE_SESSIONS_EXPIRED_CLEANED, count)

        return count

    async def complete_session(self, guild_id: int, vote_type: VoteType, result: str) -> None:
        now = UtcDateTime.now().dt
        await self._db.execute(
            """
            UPDATE vote_sessions
            SET completed_at = ?, result = ?
            WHERE guild_id = ? AND vote_type = ?
            AND completed_at IS NULL
            """,
            (UtcDateTime(now).iso, result, guild_id, vote_type.value),
        )
        logger.debug(LogTemplates.VOTE_SESSION_COMPLETED, guild_id, result)
