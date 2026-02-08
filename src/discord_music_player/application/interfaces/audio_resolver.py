"""Port interface for resolving audio tracks from queries and URLs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.entities import Track


class AudioResolver(ABC):
    """Interface for resolving URLs and search queries to playable tracks."""

    @abstractmethod
    async def resolve(self, query: str) -> "Track | None":
        """Resolve a query or URL to a playable track."""
        ...

    @abstractmethod
    async def resolve_many(self, queries: list[str]) -> list["Track"]:
        """Resolve multiple queries to tracks."""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list["Track"]:
        """Search for tracks matching a query."""
        ...

    @abstractmethod
    async def extract_playlist(self, url: str) -> list["Track"]:
        """Extract all tracks from a playlist URL."""
        ...

    @abstractmethod
    def is_url(self, query: str) -> bool:
        ...

    @abstractmethod
    def is_playlist(self, url: str) -> bool:
        ...
