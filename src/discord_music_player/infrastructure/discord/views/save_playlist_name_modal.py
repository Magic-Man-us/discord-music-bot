"""Modal that captures the name for a saved playlist."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import PlaylistConstants
from ....utils.logging import get_logger

if TYPE_CHECKING:
    from ....config.container import Container
    from ....domain.music.entities import Track

logger = get_logger(__name__)

_NAME_MAX_LEN: int = 100


class SavePlaylistNameModal(discord.ui.Modal, title="Save playlist"):
    name_input: discord.ui.TextInput[discord.ui.Modal] = discord.ui.TextInput(
        label="Playlist name",
        placeholder="my-chill-mix",
        min_length=1,
        max_length=_NAME_MAX_LEN,
        required=True,
    )

    def __init__(
        self,
        *,
        container: Container,
        tracks: list[Track],
        suggested_name: str,
    ) -> None:
        super().__init__(timeout=PlaylistConstants.VIEW_TIMEOUT)
        self._container = container
        self._tracks = tracks
        self.name_input.default = suggested_name[:_NAME_MAX_LEN]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        normalised = self.name_input.value.strip().lower()
        if not normalised:
            await interaction.response.send_message(
                "Playlist name is required.", ephemeral=True
            )
            return

        repo = self._container.saved_queue_repository
        success = await repo.save(
            guild_id=interaction.guild.id,
            name=normalised,
            tracks=self._tracks,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if success:
            await interaction.response.send_message(
                f"Saved **{len(self._tracks)}** tracks as **{normalised}**.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Too many saved playlists. Delete one first with `/playlist delete`.",
                ephemeral=True,
            )
