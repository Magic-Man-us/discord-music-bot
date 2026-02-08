"""SQLite database with per-operation connections and WAL mode."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite

from discord_music_player.domain.shared.constants import SQLPragmas
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, settings: DatabaseSettings | None = None) -> None:
        if url.startswith("sqlite:///"):
            self._db_path = url[10:]  # Remove "sqlite:///"
        else:
            self._db_path = url

        self._initialized = False
        self._keepalive_conn: aiosqlite.Connection | None = None
        self._busy_timeout = settings.busy_timeout_ms if settings else 5000
        self._connection_timeout = settings.connection_timeout_s if settings else 10

    @property
    def db_path(self) -> str:
        return self._db_path

    async def initialize(self) -> None:
        if self._initialized:
            return

        if self._db_path != ":memory:":
            db_dir = Path(self._db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

        # Keep one connection alive for in-memory DBs; otherwise the shared
        # in-memory DB is destroyed once the last connection closes.
        if self._db_path == ":memory:" and self._keepalive_conn is None:
            self._keepalive_conn = await self._connect()

        conn = self._keepalive_conn
        if conn is None:
            async with self.transaction() as conn2:
                await self._ensure_schema(conn2)
        else:
            await self._ensure_schema(conn)
            await conn.commit()

        self._initialized = True
        logger.info(LogTemplates.DATABASE_INITIALIZED, self._db_path)

    async def _ensure_schema(self, conn: aiosqlite.Connection) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_sessions (
                guild_id INTEGER PRIMARY KEY,
                state TEXT NOT NULL,
                loop_mode TEXT NOT NULL DEFAULT 'off',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                last_activity TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now'))
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS queue_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                title TEXT NOT NULL,
                webpage_url TEXT NOT NULL,
                stream_url TEXT,
                duration_seconds INTEGER,
                thumbnail_url TEXT,
                artist TEXT,
                uploader TEXT,
                like_count INTEGER,
                view_count INTEGER,
                requested_by_id INTEGER,
                requested_by_name TEXT,
                requested_at TEXT,
                position INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(guild_id) REFERENCES guild_sessions(guild_id) ON DELETE CASCADE
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_tracks_guild_pos ON queue_tracks(guild_id, position)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_queue_tracks_guild_current ON queue_tracks(guild_id, is_current)"
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                title TEXT NOT NULL,
                webpage_url TEXT NOT NULL,
                duration_seconds INTEGER,
                artist TEXT,
                uploader TEXT,
                like_count INTEGER,
                view_count INTEGER,
                requested_by_id INTEGER,
                requested_by_name TEXT,
                played_at TEXT NOT NULL,
                finished_at TEXT,
                skipped INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_history_guild_played ON track_history(guild_id, played_at)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_history_guild_track ON track_history(guild_id, track_id)"
        )

        await self._ensure_column(conn, "queue_tracks", "artist", "TEXT")
        await self._ensure_column(conn, "queue_tracks", "uploader", "TEXT")
        await self._ensure_column(conn, "queue_tracks", "like_count", "INTEGER")
        await self._ensure_column(conn, "queue_tracks", "view_count", "INTEGER")

        await self._ensure_column(conn, "track_history", "artist", "TEXT")
        await self._ensure_column(conn, "track_history", "uploader", "TEXT")
        await self._ensure_column(conn, "track_history", "like_count", "INTEGER")
        await self._ensure_column(conn, "track_history", "view_count", "INTEGER")

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vote_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                vote_type TEXT NOT NULL,
                threshold INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                result TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vote_sessions_guild ON vote_sessions(guild_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vote_sessions_guild_type ON vote_sessions(guild_id, vote_type)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vote_sessions_completed ON vote_sessions(completed_at)"
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS votes (
                vote_session_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                PRIMARY KEY (vote_session_id, user_id),
                FOREIGN KEY(vote_session_id) REFERENCES vote_sessions(id) ON DELETE CASCADE
            )
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT NOT NULL UNIQUE,
                base_track_id TEXT,
                base_track_title TEXT NOT NULL,
                base_track_artist TEXT,
                recommendations_json TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reco_cache_expires ON recommendation_cache(expires_at)"
        )

    async def _ensure_column(
        self,
        conn: aiosqlite.Connection,
        table: str,
        column: str,
        column_type_sql: str,
    ) -> None:
        rows = await conn.execute_fetchall(SQLPragmas.TABLE_INFO.format(table=table))
        existing_columns = {r[1] for r in rows}
        if column in existing_columns:
            return

        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type_sql}")
        logger.info(LogTemplates.TABLE_MIGRATED, table, column)

    async def _connect(self) -> aiosqlite.Connection:
        # SQLite ":memory:" is per-connection, so use a shared URI to allow
        # multiple connections to see the same in-memory database.
        if self._db_path == ":memory:":
            db_path = "file:discord-music-player?mode=memory&cache=shared"
            uri = True
        else:
            db_path = self._db_path
            uri = False

        conn = await aiosqlite.connect(
            db_path,
            # detect_types=0 because our ISO 8601 timestamps use 'T' separator,
            # but SQLite's built-in converter expects space-separated format.
            detect_types=0,
            uri=uri,
            timeout=self._connection_timeout,
        )
        conn.row_factory = aiosqlite.Row

        # WAL improves concurrent read behavior and reduces writer blocking.
        await conn.execute(SQLPragmas.JOURNAL_MODE_WAL)
        await conn.execute(SQLPragmas.FOREIGN_KEYS_ON)
        await conn.execute(SQLPragmas.BUSY_TIMEOUT.format(timeout=self._busy_timeout))

        return conn

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        conn = await self._connect()
        try:
            yield conn
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            raise
        finally:
            await conn.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a transaction context manager with auto-commit/rollback."""
        async with self.connection() as conn:
            try:
                yield conn
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def execute(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement.

        Note:
            This always runs in its own transaction. If you need multiple
            statements to commit/rollback together, use `transaction()` and the
            returned connection directly.
        """
        async with self.transaction() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            return cursor

    async def fetch_one(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
        """Fetch a single row."""
        async with self.connection() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all rows."""
        async with self.connection() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stats(self) -> dict[str, Any]:
        """Get database statistics.

        Returns:
            Dictionary with database statistics including file size,
            table counts, and other useful metrics.
        """
        stats: dict[str, Any] = {
            "db_path": self._db_path,
            "initialized": self._initialized,
            "tables": {},
        }

        # Get file size if exists
        db_file = Path(self._db_path)
        if db_file.exists():
            stats["file_size_bytes"] = db_file.stat().st_size
            stats["file_size_mb"] = round(db_file.stat().st_size / (1024 * 1024), 2)

        if not self._initialized:
            return stats

        try:
            async with self.connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_%'"
                )
                tables = await cursor.fetchall()

                for (table_name,) in tables:
                    count_cursor = await conn.execute(
                        f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
                    )
                    count_row = await count_cursor.fetchone()
                    stats["tables"][table_name] = count_row[0] if count_row else 0

                # Get page count and size
                page_cursor = await conn.execute(SQLPragmas.PAGE_COUNT)
                page_count_row = await page_cursor.fetchone()
                stats["page_count"] = page_count_row[0] if page_count_row else 0

                page_size_cursor = await conn.execute(SQLPragmas.PAGE_SIZE)
                page_size_row = await page_size_cursor.fetchone()
                stats["page_size"] = page_size_row[0] if page_size_row else 0

        except Exception as e:
            logger.error(LogTemplates.DATABASE_STATS_FAILED, e)
            stats["error"] = str(e)

        return stats

    async def close(self) -> None:
        """Close the database manager.

        For file-based DBs this is mostly a no-op. For in-memory DBs we also
        close the keepalive connection.
        """
        if self._keepalive_conn is not None:
            try:
                await self._keepalive_conn.close()
            finally:
                self._keepalive_conn = None
        self._initialized = False
        logger.info(LogTemplates.DATABASE_CLOSED)
