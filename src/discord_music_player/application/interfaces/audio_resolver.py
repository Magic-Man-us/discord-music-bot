"""
Audio Resolver Interface

Port interface for resolving audio tracks from queries/URLs.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.entities import Track


class AudioResolver(ABC):
    """Abstract interface for audio track resolution.

    Implementations should handle:
    - URL resolution (YouTube, SoundCloud, etc.)
    - Search queries
    - Playlist extraction
    """

    @abstractmethod
    async def resolve(self, query: str) -> "Track | None":
        """Resolve a query or URL to a playable track.

        Args:
            query: A URL or search query.

        Returns:
            A Track if resolution was successful, None otherwise.
        """
        ...

    @abstractmethod
    async def resolve_many(self, queries: list[str]) -> list["Track"]:
        """Resolve multiple queries to tracks.

        Args:
            queries: List of URLs or search queries.

        Returns:
            List of successfully resolved tracks.
        """
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 5) -> list["Track"]:
        """Search for tracks matching a query.

        Args:
            query: Search query string.
            limit: Maximum number of results.

        Returns:
            List of matching tracks.
        """
        ...

    @abstractmethod
    async def extract_playlist(self, url: str) -> list["Track"]:
        """Extract all tracks from a playlist URL.

        Args:
            url: Playlist URL.

        Returns:
            List of tracks in the playlist.
        """
        ...

    @abstractmethod
    def is_url(self, query: str) -> bool:
        """Check if a query is a URL.

        Args:
            query: Query string to check.

        Returns:
            True if the query appears to be a URL.
        """
        ...

    @abstractmethod
    def is_playlist(self, url: str) -> bool:
        """Check if a URL is a playlist.

        Args:
            url: URL to check.

        Returns:
            True if the URL appears to be a playlist.
        """
        ...
