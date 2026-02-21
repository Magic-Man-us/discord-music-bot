"""Date/time helpers for timezone-aware UTC datetimes."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from .messages import ErrorMessages
from .types import UtcDatetimeField


class UtcDateTime(BaseModel):
    """A tiny value-object wrapper around a timezone-aware UTC ``datetime``."""

    model_config = ConfigDict(frozen=True)

    dt: UtcDatetimeField

    def __init__(self, dt: datetime | None = None, /, **kwargs: object) -> None:
        """Accept ``UtcDateTime(some_dt)`` positional syntax for backward compat."""
        if dt is not None and "dt" not in kwargs:
            kwargs["dt"] = dt
        super().__init__(**kwargs)

    def __hash__(self) -> int:
        return hash(self.dt)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UtcDateTime):
            return self.dt == other.dt
        return NotImplemented

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
