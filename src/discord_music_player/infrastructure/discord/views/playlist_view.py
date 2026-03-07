"""View for previewing and selecting tracks from a YouTube playlist."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.constants import (
    DiscordEmbedLimits,
    PlaylistConstants,
)
from discord_music_player.domain.shared.messages import DiscordUIMessages
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
        title=DiscordUIMessages.EMBED_PLAYLIST_PREVIEW,
        description=DiscordUIMessages.PLAYLIST_DETECTED.format(count=len(entries)),
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


class TrackSelect(discord.ui.Select["PlaylistView"]):
    """Multi-select dropdown for picking individual tracks."""

    def __init__(self, entries: list[PlaylistEntry]) -> None:
        options = [
            discord.SelectOption(
                label=truncate(entry.title, 95),
                value=str(idx),
                description=format_duration(entry.duration_seconds) if entry.duration_seconds else None,
            )
            for idx, entry in enumerate(entries[:PlaylistConstants.MAX_SELECT_OPTIONS])
        ]
        super().__init__(
            placeholder="Pick tracks to add...",
            min_values=1,
            max_values=len(options),
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view: PlaylistView = self.view
        selected_indices = [int(v) for v in self.values]
        await view._enqueue_tracks(interaction, selected_indices)


class AddAllButton(discord.ui.Button["PlaylistView"]):
    """Add all playlist tracks to the queue."""

    def __init__(self) -> None:
        super().__init__(
            label="Add All",
            style=discord.ButtonStyle.success,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view: PlaylistView = self.view
        all_indices = list(range(len(view._entries)))
        await view._enqueue_tracks(interaction, all_indices)


class CancelButton(discord.ui.Button["PlaylistView"]):
    """Cancel playlist import."""

    def __init__(self) -> None:
        super().__init__(
            label="Cancel",
            style=discord.ButtonStyle.danger,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        view: PlaylistView = self.view
        if not view._finish_view():
            return
        view._disable_all_items()
        await interaction.response.edit_message(
            content=DiscordUIMessages.PLAYLIST_CANCELLED,
            embed=None,
            view=view,
        )


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
            self.add_item(TrackSelect(self._entries))

        self.add_item(AddAllButton())
        self.add_item(CancelButton())

    async def _enqueue_tracks(
        self, interaction: discord.Interaction, indices: list[int]
    ) -> None:
        if not self._finish_view():
            await interaction.response.send_message(
                DiscordUIMessages.PLAYLIST_ALREADY_PROCESSING, ephemeral=True
            )
            return

        self._disable_all_items()

        selected = [self._entries[i] for i in indices if i < len(self._entries)]
        await interaction.response.edit_message(
            content=DiscordUIMessages.PLAYLIST_ADDING.format(count=len(selected)),
            embed=None,
            view=self,
        )

        guild = interaction.guild
        if guild is None:
            return

        user = interaction.user
        resolver = self._container.audio_resolver
        queue_service = self._container.queue_service
        playback_service = self._container.playback_service

        added = 0
        should_start_playback = False
        for entry in selected:
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
                    if result.should_start and not should_start_playback:
                        should_start_playback = True
            except Exception:
                logger.warning("Failed to enqueue playlist track: %s", entry.title)
                continue

        if should_start_playback:
            voice_adapter = self._container.voice_adapter
            member = guild.get_member(user.id)
            if isinstance(member, discord.Member) and member.voice and member.voice.channel:
                if not voice_adapter.is_connected(guild.id):
                    connected = await voice_adapter.ensure_connected(guild.id, member.voice.channel.id)
                    if not connected:
                        logger.warning("Failed to connect to voice for playlist playback in guild %s", guild.id)
                        should_start_playback = False
            else:
                should_start_playback = False

            if should_start_playback:
                await playback_service.start_playback(guild.id)

        summary = DiscordUIMessages.PLAYLIST_ADDED.format(added=added, total=len(selected))
        try:
            await interaction.edit_original_response(content=summary, embed=None, view=None)
        except discord.HTTPException:
            pass

    async def on_timeout(self) -> None:
        if self._resolved:
            return
        self._resolved = True
        self._disable_all_items()
        if self._message is not None:
            try:
                await self._message.edit(
                    content=DiscordUIMessages.PLAYLIST_TIMEOUT,
                    embed=None,
                    view=self,
                )
            except discord.HTTPException:
                pass
