"""Select menu for choosing how many radio songs to queue."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import discord

from ....domain.shared.types import DiscordSnowflake
from ..guards.voice_guards import check_user_in_voice
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container

# callback: (interaction, count, query) -> None
StartRadioCallback = Callable[[discord.Interaction, int, str | None], Awaitable[None]]

_COUNTS: list[int] = [3, 5, 10]
_TIMEOUT: float = 30.0


class RadioCountView(BaseInteractiveView):
    """Asks the user how many songs to queue before starting radio.

    When constructed with a ``start_radio`` callback, uses that directly.
    Otherwise falls back to looking up the RadioCog at runtime (for callers
    that don't have access to the cog, e.g. NowPlayingView).
    """

    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        container: Container,
        query: str | None = None,
        start_radio: StartRadioCallback | None = None,
    ) -> None:
        super().__init__(timeout=_TIMEOUT)
        self._guild_id: DiscordSnowflake = guild_id
        self._container: Container = container
        self._query: str | None = query
        self._start_radio: StartRadioCallback | None = start_radio

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

        if self._start_radio is not None:
            await self._start_radio(interaction, count, self._query)
        else:
            # Fallback: resolve the cog at runtime to avoid circular imports
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
