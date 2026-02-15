"""View with a retry button for voice channel warmup."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.messages import DiscordUIMessages

if TYPE_CHECKING:
    from ..cogs.music_cog import MusicCog

logger = logging.getLogger(__name__)


class WarmupRetryView(discord.ui.View):
    """Shows a disabled Retry button that enables after the warmup period expires."""

    def __init__(
        self,
        *,
        remaining_seconds: int,
        query: str,
        cog: MusicCog,
    ) -> None:
        super().__init__(timeout=remaining_seconds + 120)
        self._remaining_seconds = remaining_seconds
        self._query = query
        self._cog = cog
        self._message: discord.Message | None = None
        self._enable_task: asyncio.Task[None] | None = None

    def set_message(self, message: discord.Message) -> None:
        self._message = message
        self._enable_task = asyncio.create_task(self._enable_after_warmup())

    async def _enable_after_warmup(self) -> None:
        try:
            await asyncio.sleep(self._remaining_seconds)
        except asyncio.CancelledError:
            return

        self.retry_button.disabled = False
        self.retry_button.style = discord.ButtonStyle.primary
        if self._message is not None:
            try:
                await self._message.edit(
                    content=DiscordUIMessages.STATE_VOICE_WARMUP_READY,
                    view=self,
                )
            except discord.HTTPException:
                logger.debug("Failed to edit warmup retry message")

    @discord.ui.button(label="Retry", style=discord.ButtonStyle.secondary, disabled=True)
    async def retry_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[WarmupRetryView]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass
        self.stop()
        await self._cog._execute_play(interaction, self._query)

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    async def on_timeout(self) -> None:
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                logger.debug("Failed to edit warmup retry message on timeout")
