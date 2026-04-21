"""View for previewing and selecting tracks from a YouTube playlist.

All enqueue paths (Add All, Shuffle All, per-track Select) delegate to a
single ``on_finalize`` callback so the downstream batch-resolve, summary,
and save-prompt flow is shared with the slash-param auto-enqueue path.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import discord

from ....domain.shared.constants import (
    DiscordEmbedLimits,
    PlaylistConstants,
)
from ....utils.logging import get_logger
from ....utils.playlist_select import select_playlist_items
from ....utils.reply import format_duration, truncate
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import PlaylistEntry

logger = get_logger(__name__)


class FinalizeCallback(Protocol):
    async def __call__(
        self,
        interaction: discord.Interaction,
        *,
        resolver_queries: list[str],
        source_label: str,
        suggested_name: str,
    ) -> None: ...


def build_playlist_embed(entries: list[PlaylistEntry]) -> discord.Embed:
    """Build an embed showing playlist tracks for selection."""
    embed = discord.Embed(
        title="Playlist Preview",
        description=f"Found **{len(entries)}** tracks in playlist. Select which to add:",
        color=discord.Color.blue(),
    )

    lines: list[str] = []
    for idx, entry in enumerate(entries[: PlaylistConstants.MAX_PLAYLIST_TRACKS], start=1):
        duration = format_duration(entry.duration_seconds) if entry.duration_seconds else "?"
        lines.append(f"`{idx}.` {truncate(entry.title, 55)} [{duration}]")

    chunk: list[str] = []
    chunk_len: int = 0
    field_num: int = 1
    for line in lines:
        if chunk_len + len(line) + 1 > DiscordEmbedLimits.EMBED_FIELD_CHUNK_SAFE:
            embed.add_field(
                name=f"Tracks ({field_num})" if field_num > 1 else "Tracks",
                value="\n".join(chunk),
                inline=False,
            )
            chunk = []
            chunk_len = 0
            field_num += 1
        chunk.append(line)
        chunk_len += len(line) + 1

    if chunk:
        embed.add_field(
            name=f"Tracks ({field_num})" if field_num > 1 else "Tracks",
            value="\n".join(chunk),
            inline=False,
        )

    if len(entries) > PlaylistConstants.MAX_PLAYLIST_TRACKS:
        embed.set_footer(
            text=f"Showing first {PlaylistConstants.MAX_PLAYLIST_TRACKS} of {len(entries)} tracks"
        )

    return embed


def _build_select_options(entries: list[PlaylistEntry]) -> list[discord.SelectOption]:
    """Build select menu options from playlist entries."""
    return [
        discord.SelectOption(
            label=truncate(entry.title, 95),
            value=str(idx),
            description=format_duration(entry.duration_seconds) if entry.duration_seconds else None,
        )
        for idx, entry in enumerate(entries[: PlaylistConstants.MAX_SELECT_OPTIONS])
    ]


def _suggest_name(playlist_title: str | None) -> str:
    if playlist_title:
        cleaned = playlist_title.strip().lower()
        if cleaned:
            return cleaned
    return "youtube-playlist"


class PlaylistView(BaseInteractiveView):
    """Shows playlist preview with Add All, individual select, and Cancel."""

    def __init__(
        self,
        *,
        entries: list[PlaylistEntry],
        playlist_title: str | None,
        interaction: discord.Interaction,
        container: Container,
        on_finalize: FinalizeCallback,
    ) -> None:
        super().__init__(timeout=PlaylistConstants.VIEW_TIMEOUT)
        self._entries: list[PlaylistEntry] = entries[: PlaylistConstants.MAX_PLAYLIST_TRACKS]
        self._playlist_title: str | None = playlist_title
        self._container: Container = container
        self._requester_id: int = interaction.user.id
        self._on_finalize: FinalizeCallback = on_finalize

        if len(self._entries) <= PlaylistConstants.MAX_SELECT_OPTIONS:
            options = _build_select_options(self._entries)
            select = discord.ui.Select(
                placeholder="Pick tracks to add...",
                min_values=1,
                max_values=len(options),
                options=options,
                row=0,
            )
            select.callback = self._on_select
            self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._requester_id:
            await interaction.response.send_message(
                "Only the user who requested this playlist can interact.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Add All", style=discord.ButtonStyle.success, row=1)
    async def add_all_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[PlaylistView]
    ) -> None:
        selected, _ = select_playlist_items(
            self._entries,
            count=PlaylistConstants.MAX_PLAYLIST_TRACKS,
            shuffle=False,
        )
        await self._enqueue_selection(interaction, selected)

    @discord.ui.button(label="Shuffle All", style=discord.ButtonStyle.primary, row=1)
    async def shuffle_all_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[PlaylistView]
    ) -> None:
        selected, _ = select_playlist_items(
            self._entries,
            count=PlaylistConstants.MAX_PLAYLIST_TRACKS,
            shuffle=True,
        )
        await self._enqueue_selection(interaction, selected)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[PlaylistView]
    ) -> None:
        if not self._finish_view():
            return
        self._disable_all_items()
        await interaction.response.edit_message(
            content="Playlist import cancelled.",
            embed=None,
            view=self,
        )

    async def _on_select(self, interaction: discord.Interaction) -> None:
        """Handle track selection from the dropdown."""
        for item in self.children:
            if isinstance(item, discord.ui.Select):
                selected_indices = [int(v) for v in item.values]
                selected = [
                    self._entries[i] for i in selected_indices if i < len(self._entries)
                ]
                await self._enqueue_selection(interaction, selected)
                return

    async def _enqueue_selection(
        self,
        interaction: discord.Interaction,
        entries: list[PlaylistEntry],
    ) -> None:
        if not self._finish_view():
            await interaction.response.send_message(
                "Already processing, please wait.", ephemeral=True
            )
            return

        self._disable_all_items()
        await interaction.response.edit_message(
            content=f"Resolving **{len(entries)}** track(s)…",
            embed=None,
            view=self,
        )

        if interaction.guild is None or not entries:
            return

        await self._on_finalize(
            interaction,
            resolver_queries=[entry.url for entry in entries],
            source_label="YouTube playlist",
            suggested_name=_suggest_name(self._playlist_title),
        )
