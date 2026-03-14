"""View for previewing and selecting tracks from a YouTube playlist."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.constants import (
    DiscordEmbedLimits,
    PlaylistConstants,
)
from discord_music_player.infrastructure.discord.views.base_view import (
    BaseInteractiveView,
)
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import PlaylistEntry

logger = logging.getLogger(__name__)


def build_playlist_embed(entries: list[PlaylistEntry]) -> discord.Embed:
    """Build an embed showing playlist tracks for selection."""
    embed = discord.Embed(
        title="Playlist Preview",
        description=f"Found **{len(entries)}** tracks in playlist. Select which to add:",
        color=discord.Color.blue(),
    )

    lines: list[str] = []
    for idx, entry in enumerate(entries[:PlaylistConstants.MAX_PLAYLIST_TRACKS], start=1):
        duration = format_duration(entry.duration_seconds) if entry.duration_seconds else "?"
        lines.append(f"`{idx}.` {truncate(entry.title, 55)} [{duration}]")

    # Split into fields if too long for one field
    chunk: list[str] = []
    chunk_len = 0
    field_num = 1
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
        for idx, entry in enumerate(entries[:PlaylistConstants.MAX_SELECT_OPTIONS])
    ]


class PlaylistView(BaseInteractiveView):
    """Shows playlist preview with Add All, individual select, and Cancel."""

    def __init__(
        self,
        *,
        entries: list[PlaylistEntry],
        interaction: discord.Interaction,
        container: Container,
    ) -> None:
        super().__init__(timeout=PlaylistConstants.VIEW_TIMEOUT)
        self._entries = entries[:PlaylistConstants.MAX_PLAYLIST_TRACKS]
        self._container = container

        # Only add select if entries fit (max 25 options)
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

    @discord.ui.button(label="Add All", style=discord.ButtonStyle.success, row=1)
    async def add_all_button(self, interaction: discord.Interaction, _button: discord.ui.Button[PlaylistView]) -> None:
        all_indices = list(range(len(self._entries)))
        await self._enqueue_tracks(interaction, all_indices)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
    async def cancel_button(self, interaction: discord.Interaction, _button: discord.ui.Button[PlaylistView]) -> None:
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
        # The select is dynamically added, so we find it by type
        for item in self.children:
            if isinstance(item, discord.ui.Select):
                selected_indices = [int(v) for v in item.values]
                await self._enqueue_tracks(interaction, selected_indices)
                return

    async def _enqueue_tracks(
        self, interaction: discord.Interaction, indices: list[int]
    ) -> None:
        if not self._finish_view():
            await interaction.response.send_message(
                "Already processing, please wait.", ephemeral=True
            )
            return

        self._disable_all_items()

        selected = [self._entries[i] for i in indices if i < len(self._entries)]
        await interaction.response.edit_message(
            content=f"Adding **{len(selected)}** track(s) to the queue...",
            embed=None,
            view=self,
        )

        guild = interaction.guild
        if guild is None:
            return

        user = interaction.user
        added, should_start = await self._resolve_and_enqueue(guild, user, selected)

        if should_start:
            await self._ensure_voice_and_play(guild, user)

        summary = f"Added **{added}** of **{len(selected)}** tracks to the queue."
        try:
            await interaction.edit_original_response(content=summary, embed=None, view=None)
        except discord.HTTPException:
            pass

    async def _resolve_and_enqueue(
        self,
        guild: discord.Guild,
        user: discord.User | discord.Member,
        entries: list[PlaylistEntry],
    ) -> tuple[int, bool]:
        """Resolve and enqueue entries. Returns ``(added_count, should_start_playback)``."""
        resolver = self._container.audio_resolver
        queue_service = self._container.queue_service

        added = 0
        should_start = False
        for entry in entries:
            try:
                track = await resolver.resolve(entry.url)
                if track is None:
                    continue

                result = await queue_service.enqueue(
                    guild_id=guild.id,
                    track=track,
                    user_id=user.id,
                    user_name=user.display_name,
                )
                if result.success:
                    added += 1
                    if result.should_start:
                        should_start = True
            except Exception:
                logger.warning("Failed to enqueue playlist track: %s", entry.title)
        return added, should_start

    async def _ensure_voice_and_play(
        self, guild: discord.Guild, user: discord.User | discord.Member,
    ) -> None:
        """Connect to voice (if needed) and start playback."""
        voice_adapter = self._container.voice_adapter
        member = guild.get_member(user.id)

        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            return

        if not voice_adapter.is_connected(guild.id):
            connected = await voice_adapter.ensure_connected(guild.id, member.voice.channel.id)
            if not connected:
                logger.warning("Failed to connect to voice for playlist playback in guild %s", guild.id)
                return

        await self._container.playback_service.start_playback(guild.id)

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        if self._message is not None:
            try:
                await self._message.edit(
                    content="Playlist selection timed out.",
                    embed=None,
                    view=self,
                )
            except discord.HTTPException:
                pass
