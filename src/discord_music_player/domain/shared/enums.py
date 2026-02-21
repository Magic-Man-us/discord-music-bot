"""Shared string enumerations for type-safe comparisons across cogs."""

from __future__ import annotations

from enum import StrEnum


class SyncScope(StrEnum):
    """Slash-command sync scope."""

    GUILD = "guild"
    GLOBAL = "global"


class RadioAction(StrEnum):
    """Radio command actions."""

    TOGGLE = "toggle"
    CLEAR = "clear"


class LeaderboardCategory(StrEnum):
    """Leaderboard ranking categories."""

    TRACKS = "tracks"
    USERS = "users"
    SKIPPED = "skipped"


class ActivityPeriod(StrEnum):
    """Activity chart time periods."""

    DAILY = "daily"
    WEEKLY = "weekly"
    HOURLY = "hourly"


class BotStatus(StrEnum):
    """Bot connection status labels."""

    ONLINE = "online"
    OFFLINE = "offline"
