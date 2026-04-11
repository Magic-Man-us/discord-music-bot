"""Discord UI views with YouTube and download buttons for tracks."""

from __future__ import annotations

import urllib.parse

import discord

from ....domain.shared.types import HttpUrlStr, NonEmptyStr
from .base_view import BaseInteractiveView


def build_cobalt_url(video_url: str) -> str:
    """Build a Cobalt download URL for a given video URL."""
    return f"https://cobalt.tools/#{urllib.parse.quote(video_url, safe='')}"


def add_track_link_buttons(view: discord.ui.View, webpage_url: str) -> None:
    """Add YouTube and Download link buttons to any view."""
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="YouTube",
            url=webpage_url,
        )
    )
    view.add_item(
        discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="Download",
            url=build_cobalt_url(webpage_url),
        )
    )


class DownloadView(BaseInteractiveView):
    """Link-only view for tracks (YouTube + Download buttons)."""

    def __init__(
        self,
        webpage_url: HttpUrlStr,
        title: NonEmptyStr,
        timeout: float = 300.0,
    ) -> None:
        super().__init__(timeout=timeout)

        self.webpage_url: HttpUrlStr = webpage_url
        self.title: NonEmptyStr = title
        add_track_link_buttons(self, webpage_url)
