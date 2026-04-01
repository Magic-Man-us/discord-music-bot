"""Select menu for choosing how many radio songs to queue."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.infrastructure.discord.views.base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container

_COUNTS = [3, 5, 10]
_TIMEOUT = 30.0


class RadioCountView(BaseInteractiveView):
    """Asks the user how many songs to queue before starting radio."""

    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        container: Container,
        query: str | None = None,
    ) -> None:
        super().__init__(timeout=_TIMEOUT)
        self._guild_id = guild_id
        self._container = container
        self._query = query

        select = discord.ui.Select(
            placeholder="How many songs?",
            options=[discord.SelectOption(label=f"{n} songs", value=str(n)) for n in _COUNTS],
        )
        select.callback = self._on_select
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        if not self._finish_view():
            return

        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.values:
                count = int(item.values[0])
                break
        else:
            return

        await interaction.response.defer()

        from ..cogs.radio_cog import RadioCog

        cog = interaction.client.get_cog("RadioCog")
        if not isinstance(cog, RadioCog):
            await interaction.followup.send("Radio is not available.", ephemeral=True)
            return

        await cog.start_radio(interaction, count=count, query=self._query)
        await self._delete_message()

    async def on_timeout(self) -> None:
        self._finish_view()
        await self._delete_message()
