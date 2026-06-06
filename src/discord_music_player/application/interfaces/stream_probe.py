"""Port interface for checking whether a resolved stream URL still authorizes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.shared.types import HttpHeaders, HttpUrlStr


class StreamProbe(ABC):
    """Verifies a stream URL is fetchable (not 403/4xx) before it reaches FFmpeg."""

    @abstractmethod
    async def is_playable(self, url: HttpUrlStr, headers: HttpHeaders | None = None) -> bool:
        """Return True if a ranged request to *url* with *headers* authorizes."""
        ...
