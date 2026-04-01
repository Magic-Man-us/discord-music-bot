"""SQLite database with per-operation connections and WAL mode."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

import aiosqlite
from pydantic import BaseModel, ConfigDict, Field

from ...domain.shared.constants import SQLPragmas
from ...domain.shared.types import (
    BYTES_PER_MB,
    FileBytes,
    FileSizeMB,
    NonEmptyStr,
    NonNegativeInt,
)

if TYPE_CHECKING:
    from ...config.settings import DatabaseSettings

logger = logging.getLogger(__name__)

# ── Types ─────────────────────────────────────────────────────────────

SqlParams = tuple[Any, ...] | dict[str, Any]
"""Positional (``?``) or named (``:name``) SQL parameters."""

# ── Constants ──────────────────────────────────────────────────────────

_MEMORY_PATH: Final[str] = ":memory:"

_TABLE_QUEUE_TRACKS: Final[str] = "queue_tracks"
_TABLE_TRACK_HISTORY: Final[str] = "track_history"


class _SQLiteType(StrEnum):
    """SQLite column type identifiers used in migration ALTER TABLE statements."""

    TEXT = "TEXT"
    INTEGER = "INTEGER"


# ── Schema validation models ──────────────────────────────────────────


class DatabaseStats(BaseModel):
    """Result of get_stats() — typed instead of dict[str, Any]."""

    model_config = ConfigDict(frozen=True)
    db_path: str | None = None
    initialized: bool = False
    tables: dict[str, NonNegativeInt] = Field(default_factory=dict)
    file_size_bytes: FileBytes | None = None
    file_size_mb: FileSizeMB | None = None
    page_count: NonNegativeInt | None = None
    page_size: NonNegativeInt | None = None
    error: str | None = None


class ExpectedSchema(BaseModel):
    """Expected database schema definition."""

    model_config = ConfigDict(frozen=True)
    tables: dict[str, list[str]]
    indexes: list[str]


class CountValidation(BaseModel):
    """Validation counts for a schema element category."""

    model_config = ConfigDict(frozen=False)
    expected: NonNegativeInt = 0
    found: NonNegativeInt = 0
    missing: list[NonEmptyStr] = Field(default_factory=list)


class ColumnValidation(BaseModel):
    """Validation counts for columns, with per-table missing info."""

    model_config = ConfigDict(frozen=False)
    expected: NonNegativeInt = 0
    found: NonNegativeInt = 0
    missing: dict[NonEmptyStr, list[NonEmptyStr]] = Field(default_factory=dict)


class PragmaValidation(BaseModel):
    """SQLite pragma check results."""

    model_config = ConfigDict(frozen=False)
    journal_mode: str | None = None
    foreign_keys: Literal[0, 1] | None = None


class SchemaValidationResult(BaseModel):
    """Result of validate_schema() — typed instead of dict[str, Any]."""

    model_config = ConfigDict(frozen=False)
    tables: CountValidation = Field(default_factory=CountValidation)
    columns: ColumnValidation = Field(default_factory=ColumnValidation)
    indexes: CountValidation = Field(default_factory=CountValidation)
    pragmas: PragmaValidation = Field(default_factory=PragmaValidation)
    issues: list[str] = Field(default_factory=list)


class _ExistingSchema(BaseModel):
    """Names currently present in sqlite_master."""

    model_config = ConfigDict(frozen=True)
    tables: frozenset[str]
    indexes: frozenset[str]


EXPECTED_SCHEMA = ExpectedSchema(
    tables={
        "guild_sessions": [
            "guild_id",
            "state",
            "loop_mode",
            "created_at",
            "last_activity",
            "playback_started_at",
        ],
        _TABLE_QUEUE_TRACKS: [
            "id",
            "guild_id",
            "track_id",
            "title",
            "webpage_url",
            "stream_url",
            "duration_seconds",
            "thumbnail_url",
            "artist",
            "uploader",
            "like_count",
            "view_count",
            "requested_by_id",
            "requested_by_name",
            "requested_at",
            "position",
            "is_current",
        ],
        _TABLE_TRACK_HISTORY: [
            "id",
            "guild_id",
            "track_id",
            "title",
            "webpage_url",
            "duration_seconds",
            "artist",
            "uploader",
            "like_count",
            "view_count",
            "requested_by_id",
            "requested_by_name",
            "played_at",
            "finished_at",
            "skipped",
        ],
        "vote_sessions": [
            "id",
            "guild_id",
            "track_id",
            "vote_type",
            "threshold",
            "started_at",
            "completed_at",
            "result",
        ],
        "votes": ["vote_session_id", "user_id"],
        "recommendation_cache": [
            "id",
            "cache_key",
            "base_track_id",
            "base_track_title",
            "base_track_artist",
            "recommendations_json",
            "generated_at",
            "expires_at",
        ],
        "track_genres": ["track_id", "genre", "classified_at"],
        "saved_queues": [
            "id",
            "guild_id",
            "name",
            "tracks_json",
            "track_count",
            "created_by_id",
            "created_by_name",
            "created_at",
        ],
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
        "idx_saved_queues_guild",
    ],
)


# ── Database class ────────────────────────────────────────────────────


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

    @property
    def _is_memory(self) -> bool:
        return self._db_path == _MEMORY_PATH

    async def initialize(self) -> None:
        if self._initialized:
            return

        if not self._is_memory:
            db_dir = Path(self._db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

        # Keep one connection alive for in-memory DBs; otherwise the shared
        # in-memory DB is destroyed once the last connection closes.
        if self._is_memory and self._keepalive_conn is None:
            self._keepalive_conn = await self._connect()

        conn = self._keepalive_conn
        if conn is None:
            async with self.transaction() as conn2:
                await self._ensure_schema(conn2)
        else:
            await self._ensure_schema(conn)
            await conn.commit()

        self._initialized = True
        logger.info("Database initialized at %s", self._db_path)

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

        # Migration: add columns that may not exist in older schemas
        _migration_columns = [
            ("guild_sessions", "playback_started_at", _SQLiteType.TEXT),
            (_TABLE_QUEUE_TRACKS, "artist", _SQLiteType.TEXT),
            (_TABLE_QUEUE_TRACKS, "uploader", _SQLiteType.TEXT),
            (_TABLE_QUEUE_TRACKS, "like_count", _SQLiteType.INTEGER),
            (_TABLE_QUEUE_TRACKS, "view_count", _SQLiteType.INTEGER),
            (_TABLE_TRACK_HISTORY, "artist", _SQLiteType.TEXT),
            (_TABLE_TRACK_HISTORY, "uploader", _SQLiteType.TEXT),
            (_TABLE_TRACK_HISTORY, "like_count", _SQLiteType.INTEGER),
            (_TABLE_TRACK_HISTORY, "view_count", _SQLiteType.INTEGER),
        ]
        for table, column, col_type in _migration_columns:
            await self._ensure_column(conn, table, column, col_type)

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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                title TEXT NOT NULL,
                webpage_url TEXT NOT NULL,
                duration_seconds INTEGER,
                artist TEXT,
                uploader TEXT,
                added_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                UNIQUE(user_id, track_id)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_favorites_user ON user_favorites(user_id)"
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                tracks_json TEXT NOT NULL,
                track_count INTEGER NOT NULL DEFAULT 0,
                created_by_id INTEGER NOT NULL,
                created_by_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
                UNIQUE(guild_id, name)
            )
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_saved_queues_guild ON saved_queues(guild_id)"
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
        logger.info("Migrated table %s: added column %s", table, column)

    async def _connect(self) -> aiosqlite.Connection:
        # SQLite ":memory:" is per-connection, so use a shared URI to allow
        # multiple connections to see the same in-memory database.
        if self._is_memory:
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

    async def execute(self, sql: str, parameters: SqlParams | None = None) -> aiosqlite.Cursor:
        async with self.transaction() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            return cursor

    async def fetch_one(
        self, sql: str, parameters: SqlParams | None = None
    ) -> dict[str, Any] | None:
        async with self.connection() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(
        self, sql: str, parameters: SqlParams | None = None
    ) -> list[dict[str, Any]]:
        async with self.connection() as conn:
            if parameters is not None:
                cursor = await conn.execute(sql, parameters)
            else:
                cursor = await conn.execute(sql)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_stats(self) -> DatabaseStats:
        file_size_bytes: int | None = None
        file_size_mb: float | None = None
        tables: dict[str, int] = {}
        page_count: int | None = None
        page_size: int | None = None
        error: str | None = None

        db_file = Path(self._db_path)
        if db_file.exists():
            st = db_file.stat()
            file_size_bytes = st.st_size
            file_size_mb = round(st.st_size / BYTES_PER_MB, 2)

        if self._initialized:
            try:
                async with self.connection() as conn:
                    cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    table_rows = await cursor.fetchall()

                    allowed_tables = frozenset(EXPECTED_SCHEMA.tables.keys())
                    for (table_name,) in table_rows:
                        if table_name not in allowed_tables:
                            continue
                        count_cursor = await conn.execute(
                            f"SELECT COUNT(*) FROM {table_name}"  # noqa: S608 — validated against allowlist above
                        )
                        count_row = await count_cursor.fetchone()
                        tables[table_name] = count_row[0] if count_row else 0

                    pc_cursor = await conn.execute(SQLPragmas.PAGE_COUNT)
                    pc_row = await pc_cursor.fetchone()
                    page_count = pc_row[0] if pc_row else 0

                    ps_cursor = await conn.execute(SQLPragmas.PAGE_SIZE)
                    ps_row = await ps_cursor.fetchone()
                    page_size = ps_row[0] if ps_row else 0

            except Exception as e:
                logger.error("Failed to get database stats: %s", e)
                error = str(e)

        return DatabaseStats(
            db_path=self._db_path,
            initialized=self._initialized,
            tables=tables,
            file_size_bytes=file_size_bytes,
            file_size_mb=file_size_mb,
            page_count=page_count,
            page_size=page_size,
            error=error,
        )

    # ── Schema validation (decomposed) ────────────────────────────────

    async def validate_schema(self) -> SchemaValidationResult:
        result = SchemaValidationResult()

        async with self.connection() as conn:
            existing = await self._fetch_existing_schema(conn)
            self._check_names(
                EXPECTED_SCHEMA.tables.keys(),
                existing.tables,
                result.tables,
                result.issues,
                "tables",
            )
            self._check_names(
                EXPECTED_SCHEMA.indexes, existing.indexes, result.indexes, result.issues, "indexes"
            )
            await self._check_columns(conn, EXPECTED_SCHEMA.tables, existing.tables, result)
            await self._check_pragmas(conn, result)

        return result

    @staticmethod
    async def _fetch_existing_schema(conn: aiosqlite.Connection) -> _ExistingSchema:
        """Query sqlite_master for all existing table and index names."""
        cursor = await conn.execute(
            "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'index')"
        )
        rows = await cursor.fetchall()
        tables: set[str] = set()
        indexes: set[str] = set()
        for row_type, name in rows:
            if row_type == "table":
                tables.add(name)
            else:
                indexes.add(name)
        return _ExistingSchema(tables=frozenset(tables), indexes=frozenset(indexes))

    @staticmethod
    def _check_names(
        expected: Iterable[str],
        existing: frozenset[str],
        validation: CountValidation,
        issues: list[str],
        label: str,
    ) -> None:
        """Compare expected names against existing, populating validation counts."""
        expected_list = list(expected)
        validation.expected = len(expected_list)
        missing = [name for name in expected_list if name not in existing]
        validation.found = len(expected_list) - len(missing)
        validation.missing = missing
        if missing:
            issues.append(f"Missing {label}: {', '.join(missing)}")

    @staticmethod
    async def _check_columns(
        conn: aiosqlite.Connection,
        expected_tables: dict[str, list[str]],
        existing_tables: frozenset[str],
        result: SchemaValidationResult,
    ) -> None:
        """Check that each expected table has all expected columns."""
        result.columns.expected = sum(len(cols) for cols in expected_tables.values())
        total_found = 0

        for table, expected_cols in expected_tables.items():
            if table not in existing_tables:
                result.columns.missing[table] = expected_cols
                continue

            col_rows = await conn.execute_fetchall(SQLPragmas.TABLE_INFO.format(table=table))
            existing_cols = {r[1] for r in col_rows}
            total_found += len(existing_cols & set(expected_cols))

            missing_cols = [c for c in expected_cols if c not in existing_cols]
            if missing_cols:
                result.columns.missing[table] = missing_cols
                result.issues.append(f"Missing columns in {table}: {', '.join(missing_cols)}")

        result.columns.found = total_found

    @staticmethod
    async def _check_pragmas(conn: aiosqlite.Connection, result: SchemaValidationResult) -> None:
        """Check journal_mode and foreign_keys pragmas."""
        jm_row = await (await conn.execute("PRAGMA journal_mode")).fetchone()
        result.pragmas.journal_mode = jm_row[0] if jm_row else None

        fk_row = await (await conn.execute("PRAGMA foreign_keys")).fetchone()
        result.pragmas.foreign_keys = fk_row[0] if fk_row else None

        if result.pragmas.journal_mode != "wal":
            result.issues.append(f"journal_mode is '{result.pragmas.journal_mode}', expected 'wal'")
        if result.pragmas.foreign_keys != 1:
            result.issues.append(f"foreign_keys is {result.pragmas.foreign_keys}, expected 1")

    async def close(self) -> None:
        if self._keepalive_conn is not None:
            try:
                await self._keepalive_conn.close()
            finally:
                self._keepalive_conn = None
        self._initialized = False
        logger.info("Database manager closed")
