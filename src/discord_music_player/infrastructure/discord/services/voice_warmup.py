"""In-memory per-user voice warmup gate; resets on bot restart."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil


@dataclass
class VoiceWarmupTracker:
    """Blocks interactions until a user has been in voice for ``warmup_seconds``."""

    warmup_seconds: int = 60

    def __post_init__(self) -> None:
        if self.warmup_seconds < 0:
            raise ValueError("warmup_seconds must be non-negative")
        self._joined_at: dict[tuple[int, int], datetime] = {}

    def mark_joined(
        self,
        *,
        guild_id: int,
        user_id: int,
        joined_at: datetime | None = None,
    ) -> None:
        when = joined_at or datetime.now(UTC)
        if when.tzinfo is None:
            raise ValueError("joined_at must be timezone-aware")
        self._joined_at[(guild_id, user_id)] = when

    def clear(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        """Forget any warmup state for a user."""
        self._joined_at.pop((guild_id, user_id), None)

    def remaining_seconds(
        self,
        *,
        guild_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> int:
        joined_at = self._joined_at.get((guild_id, user_id))
        if joined_at is None or self.warmup_seconds == 0:
            return 0

        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        ready_at = joined_at + timedelta(seconds=self.warmup_seconds)
        remaining = (ready_at - current).total_seconds()
        return ceil(remaining) if remaining > 0 else 0

    def is_blocked(self, *, guild_id: int, user_id: int, now: datetime | None = None) -> bool:
        """Whether the user is currently blocked by warmup."""
        return self.remaining_seconds(guild_id=guild_id, user_id=user_id, now=now) > 0
