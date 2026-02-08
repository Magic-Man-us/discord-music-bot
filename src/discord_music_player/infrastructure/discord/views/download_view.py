"""
Download View

Provides a button for users to download the current track.
"""

from __future__ import annotations

import urllib.parse

import discord


class DownloadView(discord.ui.View):
    """A view with a download button for tracks.

    Provides links to download the track via YouTube/external services.
    """

    def __init__(
        self,
        webpage_url: str,
        title: str,
        timeout: float = 300.0,  # 5 minutes
    ) -> None:
        """Initialize the download view.

        Args:
            webpage_url: The YouTube/source URL.
            title: The track title for display.
            timeout: How long the buttons remain active.
        """
        super().__init__(timeout=timeout)

        self.webpage_url = webpage_url
        self.title = title

        # Add buttons
        self._add_buttons()

    def _add_buttons(self) -> None:
        """Add the download-related buttons."""
        # YouTube link button (opens original video)
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="📺 YouTube",
                url=self.webpage_url,
            )
        )

        # Cobalt download service (privacy-respecting downloader)
        cobalt_url = f"https://cobalt.tools/#{self._encode_url(self.webpage_url)}"
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="⬇️ Download",
                url=cobalt_url,
            )
        )

    def _encode_url(self, url: str) -> str:
        """URL-encode a string for use in a URL fragment."""
        return urllib.parse.quote(url, safe="")


class NowPlayingView(discord.ui.View):
    """A view with controls for the currently playing track.

    Includes skip vote, download, and playback controls.
    """

    def __init__(
        self,
        webpage_url: str,
        title: str,
        timeout: float = 300.0,
    ) -> None:
        """Initialize the now playing view.

        Args:
            webpage_url: The YouTube/source URL.
            title: The track title.
            timeout: How long the buttons remain active.
        """
        super().__init__(timeout=timeout)

        self.webpage_url = webpage_url
        self.title = title

        self._add_buttons()

    def _add_buttons(self) -> None:
        """Add the playback control buttons."""
        # YouTube link
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="📺 YouTube",
                url=self.webpage_url,
            )
        )

        # Cobalt download
        cobalt_url = f"https://cobalt.tools/#{urllib.parse.quote(self.webpage_url, safe='')}"
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="⬇️ Download",
                url=cobalt_url,
            )
        )
