"""Discord UI views with YouTube and download buttons for tracks."""

from __future__ import annotations

import urllib.parse

import discord


class DownloadView(discord.ui.View):
    def __init__(
        self,
        webpage_url: str,
        title: str,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)

        self.webpage_url = webpage_url
        self.title = title
        self._add_buttons()

    def _add_buttons(self) -> None:
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="📺 YouTube",
                url=self.webpage_url,
            )
        )

        cobalt_url = f"https://cobalt.tools/#{self._encode_url(self.webpage_url)}"
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="⬇️ Download",
                url=cobalt_url,
            )
        )

    def _encode_url(self, url: str) -> str:
        return urllib.parse.quote(url, safe="")
