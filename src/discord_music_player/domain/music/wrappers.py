"""Immutable value-object wrappers for the music bounded context."""

from __future__ import annotations

import hashlib
import re

from pydantic import field_validator

from ..shared.types import (
    DurationSeconds,
    NonEmptyStr,
    NonNegativeInt,
    ValueWrapper,
)

_YOUTUBE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
]
_HASH_ID_LENGTH = 16


class TrackId(ValueWrapper[NonEmptyStr]):
    """Typically a YouTube video ID or a hash of the URL.

    Construct with ``TrackId(value="abc")``.
    """

    @field_validator("value")
    @classmethod
    def _reject_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Track ID cannot be empty")
        return v

    @classmethod
    def from_url(cls, url: str) -> TrackId:
        """Extract track ID from a URL, using YouTube video ID or a URL hash as fallback."""
        for pattern in _YOUTUBE_PATTERNS:
            match = pattern.search(url)
            if match:
                return cls(value=match.group(1))

        url_hash = hashlib.sha256(url.encode()).hexdigest()[:_HASH_ID_LENGTH]
        return cls(value=url_hash)


class QueuePosition(ValueWrapper[NonNegativeInt]):
    """Value object for queue positioning."""

    def next(self) -> QueuePosition:
        """Return the next position in queue."""
        return QueuePosition(value=self.value + 1)

    def previous(self) -> QueuePosition:
        """Return the previous position in queue (minimum 0)."""
        return QueuePosition(value=max(0, self.value - 1))


class StartSeconds(ValueWrapper[DurationSeconds]):
    """Validated seek offset for starting playback at a specific timestamp."""

    @classmethod
    def from_optional(cls, seconds: int | None) -> StartSeconds | None:
        """Create from an optional int, returning None if input is None or zero."""
        if seconds is None or seconds == 0:
            return None
        return cls(value=seconds)
