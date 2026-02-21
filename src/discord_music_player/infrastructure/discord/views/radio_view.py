"""View with shuffle button for radio recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class RadioView(discord.ui.View):
    """Shows a shuffle button to regenerate radio recommendations."""

    def __init__(
        self,
        *,
        guild_id: int,
        container: Container,
    ) -> None:
        super().__init__(timeout=None)  # Persistent view
        self._guild_id = guild_id
        self._container = container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="\U0001f500 Shuffle", style=discord.ButtonStyle.primary)
    async def shuffle_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[RadioView]
    ) -> None:
        """Regenerate radio recommendations."""
        await interaction.response.defer(ephemeral=True)

        # Disable radio first
        self._container.radio_service.disable_radio(self._guild_id)

        # Re-enable radio to get fresh recommendations
        user = interaction.user
        result = await self._container.radio_service.toggle_radio(
            guild_id=self._guild_id,
            user_id=user.id,
            user_name=getattr(user, "display_name", user.name),
        )

        if result.enabled:
            await interaction.followup.send(
                f"\U0001f500 Shuffled! Generated {result.tracks_added} new recommendations based on **{result.seed_title}**.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"\u274c Couldn't generate new recommendations: {result.message}",
                ephemeral=True,
            )
