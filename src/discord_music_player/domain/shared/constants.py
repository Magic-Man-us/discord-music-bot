"""Centralized constants for configuration keys, database schema, and other shared values."""

from __future__ import annotations


class ConfigKeys:
    """Configuration and environment variable key names."""

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

    # AI Settings (provider:model format, e.g. "openai:gpt-5-mini")
    OPENAI_API_KEY = "OPENAI_API_KEY"
    ANTHROPIC_API_KEY = "ANTHROPIC_API_KEY"
    GOOGLE_API_KEY = "GOOGLE_API_KEY"
    AI_MODEL = "AI_MODEL"

    # Database Settings
    DATABASE_PATH = "DATABASE_PATH"
    DATABASE_URL = "DATABASE_URL"
    DB_URL = "DB_URL"

    # Event Logging Settings
    LOG_EVENT_MESSAGES = "LOG_EVENT_MESSAGES"
    LOG_EVENT_REACTIONS = "LOG_EVENT_REACTIONS"


class SQLPragmas:
    """SQLite PRAGMA statements."""

    JOURNAL_MODE_WAL = "PRAGMA journal_mode=WAL"
    FOREIGN_KEYS_ON = "PRAGMA foreign_keys=ON"
    BUSY_TIMEOUT = "PRAGMA busy_timeout={timeout}"
    TABLE_INFO = "PRAGMA table_info({table})"
    PAGE_COUNT = "PRAGMA page_count"
    PAGE_SIZE = "PRAGMA page_size"
    EXPECTED_JOURNAL_MODE = "wal"


class AudioConstants:
    """Audio and FFmpeg configuration constants."""

    # FFmpeg Options
    FFMPEG_BEFORE_OPTIONS_DEFAULT = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    FFMPEG_OPTIONS_DEFAULT = "-vn"
    FFMPEG_FADE_IN_FILTER = '-af "afade=t=in:ss=0:d={duration}"'
    FFMPEG_USER_AGENT_HEADER = '-headers "User-Agent: {user_agent}"'

    # User Agents
    ANDROID_USER_AGENT = "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip"
    WEB_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # yt-dlp Options
    YTDLP_FORMAT_DEFAULT = "bestaudio/best"

    # Audio Settings
    DEFAULT_VOLUME = 0.5
    FADE_IN_SECONDS = 0.5
    CONNECT_TIMEOUT_SECONDS = 10.0

    # Timestamp / seek limits
    MAX_SEEK_SECONDS = 86_400  # 24 hours


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

    # Idle disconnect — leave voice after this many seconds with no playback
    IDLE_DISCONNECT_SECONDS = 300  # 5 minutes

    # Empty channel disconnect — leave voice after all users leave the channel
    EMPTY_CHANNEL_DISCONNECT_SECONDS = 30

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

    # Long track voting
    LONG_TRACK_THRESHOLD_SECONDS = 360  # 6 minutes
    LONG_TRACK_VOTE_BYPASS_LISTENERS = 4  # skip vote when <= this many listeners

    # Discord limits
    MAX_DISCORD_SNOWFLAKE = 2**64
    MIN_COMMAND_PREFIX_LENGTH = 1
    MAX_COMMAND_PREFIX_LENGTH = 5


class DiscordEmbedLimits:
    """Discord API embed and message size constraints."""

    EMBED_FIELD_VALUE_MAX = 1024
    EMBED_FIELD_CHUNK_SAFE = 1000  # Safe margin below EMBED_FIELD_VALUE_MAX
    SLASH_STATUS_TRUNCATION = 500
    MESSAGE_CONTENT_SNIPPET = 256


class HealthConstants:
    """Health monitoring thresholds and intervals."""

    DEFAULT_FAST_INTERVAL = 180
    DEFAULT_DETAILED_INTERVAL = 300
    LATENCY_OK_MS = 200
    LATENCY_WARN_MS = 800
    LATENCY_RESET_FACTOR = 0.6


class AnalyticsConstants:
    """Analytics and charting defaults."""

    BLURPLE = 0x5865F2
    CHART_LABEL_TRUNCATION = 40
    LEADERBOARD_LINE_TRUNCATION = 50
    DEFAULT_LEADERBOARD_LIMIT = 10
    ACTIVITY_CHART_FILENAME = "activity.png"
    GENRE_TOP_N = 10
    ACTIVITY_DAYS_WINDOW = 30

    CHART_BG_COLOR = "#2C2F33"
    CHART_TEXT_COLOR = "#FFFFFF"
    CHART_ACCENT_COLOR = "#5865F2"
    CHART_GRID_COLOR = "#40444B"
    CHART_DPI = 100
    CHART_LABEL_FONTSIZE = 9
    CHART_TITLE_FONTSIZE = 14
    CHART_VALUE_LABEL_OFFSET = 0.01


class PlaylistConstants:
    """Playlist import limits."""

    MAX_SELECT_OPTIONS = 25  # Discord select menu limit
    MAX_PLAYLIST_TRACKS = 50  # Max tracks to show from a playlist
    VIEW_TIMEOUT = 120.0  # 2 minutes

class UIConstants:
    """Cross-cog UI presentation constants."""

    TITLE_TRUNCATION = 80
    QUEUE_PER_PAGE = 10
    UNKNOWN_FALLBACK = "Unknown"
    EVERYONE_ROLE = "@everyone"
    MS_PER_SECOND = 1000

    # Embed field names
    FIELD_CREATED = "Created"

    # Display limits
    MAX_DISPLAY_ROLES = 10
    MAX_DISPLAY_FEATURES = 10

    # Embed text
    NEXT_UP_NONE = "No Track Queued"

    # Auto-delete timers (seconds)
    FINISHED_DELETE_AFTER = 30.0
    QUEUED_DELETE_AFTER = 15.0

    # Voice guard messages
    NOT_IN_VOICE = "You need to be in a voice channel first."
