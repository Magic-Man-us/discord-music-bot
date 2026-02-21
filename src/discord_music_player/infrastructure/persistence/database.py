"""SQLite database with per-operation connections and WAL mode."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

from discord_music_player.domain.shared.constants import SQLPragmas
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


class DatabaseStats(BaseModel):
    """Result of get_stats() — typed instead of dict[str, Any]."""

    model_config = ConfigDict(frozen=False)
    db_path: str = ""
    initialized: bool = False
    tables: dict[str, int] = Field(default_factory=dict)
    file_size_bytes: int | None = None
    file_size_mb: float | None = None
    page_count: int | None = None
    page_size: int | None = None
    error: str | None = None


class ExpectedSchema(BaseModel):
    """Expected database schema definition."""

    model_config = ConfigDict(frozen=True)
    tables: dict[str, list[str]]
    indexes: list[str]


class CountValidation(BaseModel):
    """Validation counts for a schema element category."""

    model_config = ConfigDict(frozen=False)
    expected: int = 0
    found: int = 0
    missing: list[str] = Field(default_factory=list)


class ColumnValidation(BaseModel):
    """Validation counts for columns, with per-table missing info."""

    model_config = ConfigDict(frozen=False)
    expected: int = 0
    found: int = 0
    missing: dict[str, list[str]] = Field(default_factory=dict)


class PragmaValidation(BaseModel):
    """SQLite pragma check results."""

    model_config = ConfigDict(frozen=False)
    journal_mode: str | None = None
    foreign_keys: int | None = None


class SchemaValidationResult(BaseModel):
    """Result of validate_schema() — typed instead of dict[str, Any]."""

    model_config = ConfigDict(frozen=False)
    tables: CountValidation = Field(default_factory=CountValidation)
    columns: ColumnValidation = Field(default_factory=ColumnValidation)
    indexes: CountValidation = Field(default_factory=CountValidation)
    pragmas: PragmaValidation = Field(default_factory=PragmaValidation)
    issues: list[str] = Field(default_factory=list)


EXPECTED_SCHEMA = ExpectedSchema(
    tables={
        "guild_sessions": [
            "guild_id", "state", "loop_mode", "created_at", "last_activity",
        ],
        "queue_tracks": [
            "id", "guild_id", "track_id", "title", "webpage_url", "stream_url",
            "duration_seconds", "thumbnail_url", "artist", "uploader", "like_count",
            "view_count", "requested_by_id", "requested_by_name", "requested_at",
            "position", "is_current",
        ],
        "track_history": [
            "id", "guild_id", "track_id", "title", "webpage_url", "duration_seconds",
            "artist", "uploader", "like_count", "view_count", "requested_by_id",
            "requested_by_name", "played_at", "finished_at", "skipped",
        ],
        "vote_sessions": [
            "id", "guild_id", "track_id", "vote_type", "threshold",
            "started_at", "completed_at", "result",
        ],
        "votes": ["vote_session_id", "user_id"],
        "recommendation_cache": [
            "id", "cache_key", "base_track_id", "base_track_title",
            "base_track_artist", "recommendations_json", "generated_at", "expires_at",
        ],
        "track_genres": ["track_id", "genre", "classified_at"],
    },
    indexes=[
        "idx_queue_tracks_guild_pos",
        "idx_queue_tracks_guild_current",
        "idx_track_history_guild_played",
        "idx_track_history_guild_track",
        "idx_vote_sessions_guild",
        "idx_vote_sessions_guild_type",
        "idx_vote_sessions_completed",
        "idx_reco_cache_expires",
        "idx_track_genres_genre",
    ],
)


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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_genres (
                track_id TEXT PRIMARY KEY,
                genre TEXT NOT NULL,
                classified_at TEXT NOT NULL
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_genres_genre ON track_genres(genre)"
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
        async with self.transaction() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            return cursor

    async def fetch_one(
        self, sql: str, parameters: tuple[Any, ...] | None = None
    ) -> dict[str, Any] | None:
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
        async with self.connection() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stats(self) -> DatabaseStats:
        stats = DatabaseStats(
            db_path=self._db_path,
            initialized=self._initialized,
        )

        db_file = Path(self._db_path)
        if db_file.exists():
            st = db_file.stat()
            stats.file_size_bytes = st.st_size
            stats.file_size_mb = round(st.st_size / (1024 * 1024), 2)

        if not self._initialized:
            return stats

        try:
            async with self.connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = await cursor.fetchall()

                for (table_name,) in tables:
                    count_cursor = await conn.execute(
                        f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608
                    )
                    count_row = await count_cursor.fetchone()
                    stats.tables[table_name] = count_row[0] if count_row else 0

                page_cursor = await conn.execute(SQLPragmas.PAGE_COUNT)
                page_count_row = await page_cursor.fetchone()
                stats.page_count = page_count_row[0] if page_count_row else 0

                page_size_cursor = await conn.execute(SQLPragmas.PAGE_SIZE)
                page_size_row = await page_size_cursor.fetchone()
                stats.page_size = page_size_row[0] if page_size_row else 0

        except Exception as e:
            logger.error(LogTemplates.DATABASE_STATS_FAILED, e)
            stats.error = str(e)

        return stats

    async def validate_schema(self) -> SchemaValidationResult:
        result = SchemaValidationResult()

        expected_tables = EXPECTED_SCHEMA.tables
        expected_indexes = EXPECTED_SCHEMA.indexes

        result.tables.expected = len(expected_tables)
        result.indexes.expected = len(expected_indexes)

        total_expected_cols = sum(len(cols) for cols in expected_tables.values())
        result.columns.expected = total_expected_cols

        async with self.connection() as conn:
            # Check tables
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            rows = await cursor.fetchall()
            existing_tables = {row[0] for row in rows}

            found_tables = [t for t in expected_tables if t in existing_tables]
            missing_tables = [t for t in expected_tables if t not in existing_tables]
            result.tables.found = len(found_tables)
            result.tables.missing = missing_tables

            if missing_tables:
                result.issues.append(f"Missing tables: {', '.join(missing_tables)}")

            # Check columns per table
            total_found_cols = 0
            for table, expected_cols in expected_tables.items():
                if table not in existing_tables:
                    result.columns.missing[table] = expected_cols
                    continue

                col_rows = await conn.execute_fetchall(
                    SQLPragmas.TABLE_INFO.format(table=table)
                )
                existing_cols = {r[1] for r in col_rows}
                total_found_cols += len(existing_cols & set(expected_cols))

                missing_cols = [c for c in expected_cols if c not in existing_cols]
                if missing_cols:
                    result.columns.missing[table] = missing_cols
                    result.issues.append(
                        f"Missing columns in {table}: {', '.join(missing_cols)}"
                    )

            result.columns.found = total_found_cols

            # Check indexes
            idx_cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            idx_rows = await idx_cursor.fetchall()
            existing_indexes = {row[0] for row in idx_rows}

            found_indexes = [i for i in expected_indexes if i in existing_indexes]
            missing_indexes = [i for i in expected_indexes if i not in existing_indexes]
            result.indexes.found = len(found_indexes)
            result.indexes.missing = missing_indexes

            if missing_indexes:
                result.issues.append(
                    f"Missing indexes: {', '.join(missing_indexes)}"
                )

            # Check pragmas
            jm_cursor = await conn.execute("PRAGMA journal_mode")
            jm_row = await jm_cursor.fetchone()
            journal_mode = jm_row[0] if jm_row else None
            result.pragmas.journal_mode = journal_mode

            fk_cursor = await conn.execute("PRAGMA foreign_keys")
            fk_row = await fk_cursor.fetchone()
            foreign_keys = fk_row[0] if fk_row else None
            result.pragmas.foreign_keys = foreign_keys

            if journal_mode != "wal":
                result.issues.append(
                    f"journal_mode is '{journal_mode}', expected 'wal'"
                )
            if foreign_keys != 1:
                result.issues.append(
                    f"foreign_keys is {foreign_keys}, expected 1"
                )

        return result

    async def close(self) -> None:
        if self._keepalive_conn is not None:
            try:
                await self._keepalive_conn.close()
            finally:
                self._keepalive_conn = None
        self._initialized = False
        logger.info(LogTemplates.DATABASE_CLOSED)
