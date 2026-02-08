"""Centralized constants for configuration keys, database schema, and other shared values.

This module provides reusable constants that reduce magic strings and improve maintainability.
"""

from __future__ import annotations


class ConfigKeys:
    """Configuration and environment variable key names.

    These constants centralize all configuration keys used across the application.
    While Pydantic Settings already provides type-safe access, these constants
    ensure consistency when accessing raw environment variables or config files.
    """

    # Top-level Settings
    ENVIRONMENT = "ENVIRONMENT"
    DEBUG = "DEBUG"
    LOG_LEVEL = "LOG_LEVEL"

    # Discord Settings
    DISCORD_TOKEN = "DISCORD_TOKEN"
    DISCORD_BOT_TOKEN = "DISCORD__BOT_TOKEN"  # Nested delimiter format
    DISCORD_COMMAND_PREFIX = "DISCORD_COMMAND_PREFIX"
    DISCORD__COMMAND_PREFIX = "DISCORD__COMMAND_PREFIX"  # Nested delimiter format
    OWNER_IDS = "OWNER_IDS"
    GUILD_IDS = "GUILD_IDS"
    TEST_GUILD_IDS = "TEST_GUILD_IDS"

    # AI/OpenAI Settings
    OPENAI_API_KEY = "OPENAI_API_KEY"
    AI_MODEL = "AI_MODEL"
    OPENAI_MODEL = "OPENAI_MODEL"

    # Database Settings
    DATABASE_PATH = "DATABASE_PATH"
    DATABASE_URL = "DATABASE_URL"
    DB_URL = "DB_URL"

    # Event Logging Settings
    LOG_EVENT_MESSAGES = "LOG_EVENT_MESSAGES"
    LOG_EVENT_REACTIONS = "LOG_EVENT_REACTIONS"


class DatabaseTables:
    """Database table names.

    Centralizing table names prevents typos in SQL queries and makes
    schema changes easier to track.
    """

    GUILD_SESSIONS = "guild_sessions"
    QUEUE_TRACKS = "queue_tracks"
    TRACK_HISTORY = "track_history"
    VOTE_SESSIONS = "vote_sessions"
    VOTES = "votes"
    RECOMMENDATION_CACHE = "recommendation_cache"


class DatabaseColumns:
    """Database column names.

    Centralizing column names ensures consistency across repositories
    and makes refactoring safer.
    """

    # Primary Keys
    ID = "id"

    # Foreign Keys & IDs
    GUILD_ID = "guild_id"
    USER_ID = "user_id"
    TRACK_ID = "track_id"
    VOTE_SESSION_ID = "vote_session_id"
    BASE_TRACK_ID = "base_track_id"

    # Track Fields
    TITLE = "title"
    WEBPAGE_URL = "webpage_url"
    STREAM_URL = "stream_url"
    DURATION_SECONDS = "duration_seconds"
    THUMBNAIL_URL = "thumbnail_url"
    ARTIST = "artist"
    UPLOADER = "uploader"
    LIKE_COUNT = "like_count"
    VIEW_COUNT = "view_count"

    # Requester Fields
    REQUESTED_BY_ID = "requested_by_id"
    REQUESTED_BY_NAME = "requested_by_name"
    REQUESTED_AT = "requested_at"

    # Queue Fields
    POSITION = "position"
    IS_CURRENT = "is_current"

    # Session Fields
    STATE = "state"
    LOOP_MODE = "loop_mode"
    CREATED_AT = "created_at"
    LAST_ACTIVITY = "last_activity"

    # History Fields
    PLAYED_AT = "played_at"
    FINISHED_AT = "finished_at"
    SKIPPED = "skipped"

    # Vote Fields
    VOTE_TYPE = "vote_type"
    THRESHOLD = "threshold"
    STARTED_AT = "started_at"
    COMPLETED_AT = "completed_at"
    RESULT = "result"

    # Cache Fields
    CACHE_KEY = "cache_key"
    BASE_TRACK_TITLE = "base_track_title"
    BASE_TRACK_ARTIST = "base_track_artist"
    RECOMMENDATIONS_JSON = "recommendations_json"
    GENERATED_AT = "generated_at"
    EXPIRES_AT = "expires_at"


class SQLPragmas:
    """SQLite PRAGMA statements for database configuration.

    These pragmas are applied to each connection to ensure consistent behavior.
    """

    JOURNAL_MODE_WAL = "PRAGMA journal_mode=WAL"
    FOREIGN_KEYS_ON = "PRAGMA foreign_keys=ON"
    BUSY_TIMEOUT = "PRAGMA busy_timeout={timeout}"
    TABLE_INFO = "PRAGMA table_info({table})"
    PAGE_COUNT = "PRAGMA page_count"
    PAGE_SIZE = "PRAGMA page_size"


class SQLQueries:
    """Common SQL query patterns.

    Extract frequently used SQL fragments to ensure consistency
    and make it easier to spot potential SQL injection risks.
    """

    # Table metadata queries
    GET_TABLE_NAMES = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%_%'"
    GET_TABLE_INFO = "PRAGMA table_info({table})"

    # Count queries
    COUNT_ALL = "SELECT COUNT(*) as count FROM {table}"
    COUNT_WHERE = "SELECT COUNT(*) as count FROM {table} WHERE {condition}"

    # Index creation templates
    CREATE_INDEX = "CREATE INDEX IF NOT EXISTS {index_name} ON {table}({columns})"

    # Alter table template
    ALTER_TABLE_ADD_COLUMN = "ALTER TABLE {table} ADD COLUMN {column} {column_type}"


class AudioConstants:
    """Audio and FFmpeg configuration constants."""

    # FFmpeg Options
    FFMPEG_BEFORE_OPTIONS_DEFAULT = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    FFMPEG_OPTIONS_DEFAULT = "-vn"  # No video
    FFMPEG_FADE_IN_FILTER = '-af "afade=t=in:ss=0:d={duration}"'
    FFMPEG_USER_AGENT_HEADER = '-headers "User-Agent: {user_agent}"'

    # User Agents
    ANDROID_USER_AGENT = "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip"

    # yt-dlp Options
    YTDLP_FORMAT_DEFAULT = "bestaudio/best"

    # Audio Settings
    DEFAULT_VOLUME = 0.5
    FADE_IN_SECONDS = 0.5
    CONNECT_TIMEOUT_SECONDS = 10.0


class DatabaseURLSchemes:
    """Valid database URL schemes for validation."""

    SQLITE = "sqlite://"
    POSTGRESQL = "postgresql://"
    MYSQL = "mysql://"

    # For in-memory testing
    MEMORY = ":memory:"
    MEMORY_SHARED_URI = "file:discord-music-player?mode=memory&cache=shared"


class LogLevels:
    """Valid logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class EnvironmentTypes:
    """Valid environment types."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"


class HTTPHeaders:
    """HTTP header names and common values."""

    USER_AGENT = "User-Agent"
    CONTENT_TYPE = "Content-Type"
    AUTHORIZATION = "Authorization"

    # Common content types
    JSON = "application/json"
    FORM_URLENCODED = "application/x-www-form-urlencoded"


class TimeConstants:
    """Time-related constants in seconds."""

    # Connection timeouts
    VOICE_CONNECT_TIMEOUT = 10.0
    DATABASE_CONNECTION_TIMEOUT = 10.0

    # Cache TTLs
    DEFAULT_CACHE_TTL = 3600  # 1 hour
    SHORT_CACHE_TTL = 300  # 5 minutes
    LONG_CACHE_TTL = 86400  # 24 hours

    # Cleanup intervals
    CLEANUP_INTERVAL_MINUTES = 30
    STALE_SESSION_HOURS = 24

    # Voice warmup
    VOICE_WARMUP_SECONDS = 60

    # Busy timeout for SQLite
    DEFAULT_BUSY_TIMEOUT_MS = 5000


class LimitConstants:
    """Numeric limits and constraints."""

    # Queue limits
    MAX_QUEUE_SIZE = 50
    MIN_QUEUE_SIZE = 1

    # Volume limits
    MIN_VOLUME = 0.0
    MAX_VOLUME = 2.0
    DEFAULT_VOLUME = 0.5

    # Recommendation limits
    MIN_RECOMMENDATION_COUNT = 1
    MAX_RECOMMENDATION_COUNT = 10

    # Database limits
    MIN_POOL_SIZE = 1
    MAX_POOL_SIZE = 100

    # Token limits (API)
    MAX_TOKENS_DEFAULT = 500
    MIN_TOKENS = 1
    MAX_TOKENS = 4096

    # Temperature limits (AI)
    MIN_TEMPERATURE = 0.0
    MAX_TEMPERATURE = 2.0
    DEFAULT_TEMPERATURE = 0.7

    # Voting limits
    MIN_VOTERS = 1
    MIN_SKIP_THRESHOLD_PERCENTAGE = 0.0
    MAX_SKIP_THRESHOLD_PERCENTAGE = 1.0
    DEFAULT_SKIP_THRESHOLD_PERCENTAGE = 0.5
    DEFAULT_AUTO_SKIP_LISTENER_COUNT = 2

    # Discord limits
    MAX_DISCORD_SNOWFLAKE = 2**64
    MIN_COMMAND_PREFIX_LENGTH = 1
    MAX_COMMAND_PREFIX_LENGTH = 5
