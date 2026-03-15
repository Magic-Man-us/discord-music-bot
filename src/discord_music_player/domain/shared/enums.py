"""Shared string enumerations for type-safe comparisons across cogs."""

from __future__ import annotations

from enum import StrEnum


class SyncScope(StrEnum):
    """Slash-command sync scope."""

    GUILD = "guild"
    GLOBAL = "global"


class RadioAction(StrEnum):

    ON = "on"
    OFF = "off"


class LeaderboardCategory(StrEnum):
    """Leaderboard ranking categories."""

    TRACKS = "tracks"
    USERS = "users"
    SKIPPED = "skipped"


class LeaderboardTimeRange(StrEnum):
    """Time range for leaderboard queries."""

    ALL_TIME = "all"
    LAST_7_DAYS = "7d"
    LAST_30_DAYS = "30d"


class ActivityPeriod(StrEnum):
    """Activity chart time periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    HOURLY = "hourly"


class BotStatus(StrEnum):
    """Bot connection status labels."""

    ONLINE = "online"
    OFFLINE = "offline"


class LogLevel(StrEnum):
    """Valid logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Weekday(StrEnum):
    """Weekday short names ordered Sunday=0 to match SQLite strftime('%w')."""

    SUN = "Sun"
    MON = "Mon"
    TUE = "Tue"
    WED = "Wed"
    THU = "Thu"
    FRI = "Fri"
    SAT = "Sat"


class EnvironmentType(StrEnum):
    """Valid environment types."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"
