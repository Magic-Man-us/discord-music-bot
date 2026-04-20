"""Count-picker view for external playlist imports."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import PlaylistConstants
from ....utils.logging import get_logger
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container

logger = get_logger(__name__)


class ExternalPlaylistCountView(BaseInteractiveView):
    """Preset buttons (5 / 10 / 25 / All) + Cancel.

    ``queries`` is the full, pre-resolved ``"Artist - Title"`` list returned
    by the external source; resolution against yt-dlp only happens after the
    user commits to a size, so we don't waste resolver budget on rejects.
    """

    def __init__(
        self,
        *,
        queries: list[str],
        interaction: discord.Interaction,
        container: Container,
        source_label: str,
    ) -> None:
        super().__init__(timeout=PlaylistConstants.VIEW_TIMEOUT)
        self._queries: list[str] = queries
        self._requester_id: int = interaction.user.id
        self._container: Container = container
        self._source_label: str = source_label

        total = len(queries)
        all_cap = min(total, PlaylistConstants.MAX_PLAYLIST_TRACKS)

        for count in PlaylistConstants.EXTERNAL_COUNT_PRESETS:
            if count >= all_cap:
                continue
            self.add_item(self._make_count_button(count, style=discord.ButtonStyle.primary))

        self.add_item(
            self._make_count_button(
                all_cap,
                style=discord.ButtonStyle.success,
                label=(
                    f"Play all ({all_cap})"
                    if total <= PlaylistConstants.MAX_PLAYLIST_TRACKS
                    else f"Play first {all_cap} of {total}"
                ),
            )
        )

        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger, row=1)
        cancel.callback = self._cancel
        self.add_item(cancel)

    def _make_count_button(
        self,
        count: int,
        *,
        style: discord.ButtonStyle,
        label: str | None = None,
    ) -> discord.ui.Button[ExternalPlaylistCountView]:
        btn: discord.ui.Button[ExternalPlaylistCountView] = discord.ui.Button(
            label=label or f"Play {count}",
            style=style,
            row=0,
        )

        async def _callback(interaction: discord.Interaction) -> None:
            await self._resolve_and_enqueue(interaction, count)

        btn.callback = _callback
        return btn

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._requester_id:
            await interaction.response.send_message(
                "Only the user who ran /play can pick.", ephemeral=True
            )
            return False
        return True

    async def _resolve_and_enqueue(
        self, interaction: discord.Interaction, count: int
    ) -> None:
        if not self._finish_view():
            await interaction.response.send_message(
                "Already processing…", ephemeral=True
            )
            return

        self._disable_all_items()

        guild = interaction.guild
        if guild is None:
            await interaction.response.edit_message(
                content="This command only works in a server.", view=None
            )
            return

        await interaction.response.edit_message(
            content=f"Resolving **{count}** tracks from {self._source_label} on YouTube…",
            view=self,
        )

        subset = self._queries[:count]
        tracks = await self._container.audio_resolver.resolve_many(subset)
        if not tracks:
            await interaction.edit_original_response(
                content="Couldn't find any of those tracks on YouTube.",
                view=None,
            )
            return

        user = interaction.user
        result = await self._container.queue_service.enqueue_batch(
            guild_id=guild.id,
            tracks=tracks,
            user_id=user.id,
            user_name=user.display_name,
        )
        if result.should_start:
            await self._container.playback_service.start_playback(guild.id)

        await interaction.edit_original_response(
            content=(
                f"Queued **{result.enqueued}/{count}** tracks from {self._source_label}."
            ),
            view=None,
        )

    async def _cancel(self, interaction: discord.Interaction) -> None:
        if not self._finish_view():
            return
        self._disable_all_items()
        await interaction.response.edit_message(
            content="Import cancelled.", view=self
        )
