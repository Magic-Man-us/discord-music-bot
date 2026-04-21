"""Ephemeral post-import prompt: "Save this as a named playlist?"."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import PlaylistConstants
from ....utils.logging import get_logger
from .base_view import BaseInteractiveView
from .save_playlist_name_modal import SavePlaylistNameModal

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = get_logger(__name__)


class SavePlaylistPromptView(BaseInteractiveView):
    def __init__(
        self,
        *,
        container: Container,
        tracks: list[Track],
        suggested_name: str,
        requester_id: int,
    ) -> None:
        super().__init__(timeout=PlaylistConstants.VIEW_TIMEOUT)
        self._container = container
        self._tracks = tracks
        self._suggested_name = suggested_name
        self._requester_id = requester_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self._requester_id:
            await interaction.response.send_message(
                "Only the user who ran /play can save this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Save as…", style=discord.ButtonStyle.success)
    async def save_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[SavePlaylistPromptView],
    ) -> None:
        if not self._finish_view():
            return
        modal = SavePlaylistNameModal(
            container=self._container,
            tracks=self._tracks,
            suggested_name=self._suggested_name,
        )
        await interaction.response.send_modal(modal)
        await self._delete_message(delay=0)

    @discord.ui.button(label="No thanks", style=discord.ButtonStyle.secondary)
    async def dismiss_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[SavePlaylistPromptView],
    ) -> None:
        if not self._finish_view():
            return
        self._disable_all_items()
        await interaction.response.edit_message(content="OK, not saving.", view=None)
