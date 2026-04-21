"""Port interface for resolving audio tracks from queries and URLs."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ...domain.shared.types import HttpUrlStr, NonEmptyStr, PositiveInt

if TYPE_CHECKING:
    from ...domain.music.entities import PlaylistPreview, Track


class AudioResolver(ABC):
    """Interface for resolving URLs and search queries to playable tracks."""

    @abstractmethod
    async def resolve(self, query: NonEmptyStr) -> Track | None:
        """Resolve a query or URL to a playable track."""
        ...

    @abstractmethod
    async def resolve_many(self, queries: list[NonEmptyStr]) -> list[Track]:
        """Resolve multiple queries to tracks."""
        ...

    @abstractmethod
    async def search(self, query: NonEmptyStr, limit: PositiveInt = 5) -> list[Track]:
        """Search for tracks matching a query."""
        ...

    @abstractmethod
    async def extract_playlist(self, url: HttpUrlStr) -> list[Track]:
        """Extract all tracks from a playlist URL."""
        ...

    @abstractmethod
    async def preview_playlist(self, url: HttpUrlStr) -> PlaylistPreview:
        """Extract playlist title + lightweight track metadata, no stream resolution."""
        ...

    @abstractmethod
    def is_url(self, query: NonEmptyStr) -> bool: ...

    @abstractmethod
    def is_playlist(self, url: HttpUrlStr) -> bool: ...
