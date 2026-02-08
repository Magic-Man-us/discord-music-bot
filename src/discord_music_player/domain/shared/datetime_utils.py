"""Date/time helpers.

Goal: centralize all date/time serialization + parsing.

- Always store and operate on timezone-aware UTC datetimes.
- Provide common string formats used across the app (DB, logs, Discord).

This module is intentionally dependency-free and safe to use in any layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ...domain.shared.messages import ErrorMessages


@dataclass(frozen=True, slots=True)
class UtcDateTime:
    """A tiny value-object wrapper around a timezone-aware UTC `datetime`."""

    dt: datetime

    def __post_init__(self) -> None:
        if self.dt.tzinfo is None:
            raise ValueError(ErrorMessages.TIMEZONE_REQUIRED_UTC_DATETIME)
        # Normalize to UTC
        object.__setattr__(self, "dt", self.dt.astimezone(UTC))

    # ---- Constructors ----

    @classmethod
    def now(cls) -> UtcDateTime:
        return cls(datetime.now(UTC))

    @classmethod
    def from_iso(cls, value: str) -> UtcDateTime:
        # Accepts: '...+00:00' or '...Z'
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return cls(datetime.fromisoformat(value))

    @classmethod
    def from_unix_seconds(cls, seconds: int) -> UtcDateTime:
        return cls(datetime.fromtimestamp(int(seconds), tz=UTC))

    # ---- Computed fields / formats ----

    @property
    def iso(self) -> str:
        """RFC3339/ISO8601 with explicit offset (+00:00)."""
        return self.dt.isoformat()

    @property
    def iso_z(self) -> str:
        """RFC3339 with trailing 'Z'."""
        # Ensure +00:00 formatting is present then replace.
        return self.dt.isoformat().replace("+00:00", "Z")

    @property
    def unix_seconds(self) -> int:
        return int(self.dt.timestamp())

    @property
    def unix_millis(self) -> int:
        return int(self.dt.timestamp() * 1000)

    @property
    def human_utc(self) -> str:
        return self.dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    def discord_timestamp(self, style: str = "R") -> str:
        """Discord timestamp markup.

        Styles: https://discord.com/developers/docs/reference#message-formatting-timestamp-styles
        Common: 'R' (relative), 'f' (short datetime).
        """
        return f"<t:{self.unix_seconds}:{style}>"


def utcnow() -> datetime:
    """Preferred replacement for `datetime.now(UTC)()`.

    Returns a timezone-aware datetime in UTC.
    """
    return datetime.now(UTC)
