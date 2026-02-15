"""View with shuffle button for radio recommendations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from ..cogs.music_cog import MusicCog

logger = logging.getLogger(__name__)


class RadioView(discord.ui.View):
    """Shows a shuffle button to regenerate radio recommendations."""

    def __init__(
        self,
        *,
        guild_id: int,
        cog: MusicCog,
    ) -> None:
        super().__init__(timeout=None)  # Persistent view
        self._guild_id = guild_id
        self._cog = cog

    @discord.ui.button(label="🔀 Shuffle", style=discord.ButtonStyle.primary)
    async def shuffle_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[RadioView]
    ) -> None:
        """Regenerate radio recommendations."""
        await interaction.response.defer(ephemeral=True)

        # Disable radio first
        self._cog.container.radio_service.disable_radio(self._guild_id)

        # Re-enable radio to get fresh recommendations
        user = interaction.user
        result = await self._cog.container.radio_service.toggle_radio(
            guild_id=self._guild_id,
            user_id=user.id,
            user_name=getattr(user, "display_name", user.name),
        )

        if result.enabled:
            await interaction.followup.send(
                f"🔀 Shuffled! Generated {result.tracks_added} new recommendations based on **{result.seed_title}**.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"❌ Couldn't generate new recommendations: {result.message}",
                ephemeral=True,
            )
