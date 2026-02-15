"""View prompting users to resume playback after bot restart."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from ....application.services.playback_service import PlaybackApplicationService

logger = logging.getLogger(__name__)


class ResumePlaybackView(discord.ui.View):
    def __init__(
        self,
        *,
        guild_id: int,
        channel_id: int,
        playback_service: PlaybackApplicationService,
        track_title: str,
    ) -> None:
        super().__init__(timeout=30.0)
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._playback_service = playback_service
        self._track_title = track_title
        self._message: discord.Message | None = None

    def set_message(self, message: discord.Message) -> None:
        self._message = message

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.green)
    async def resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        await self._playback_service.start_playback(self._guild_id)
        await self._finish(interaction, f"▶️ Resumed playback: **{self._track_title}**")

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.red)
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        await self._playback_service.stop_playback(self._guild_id)
        await self._finish(interaction, "⏭️ Skipped. Playback cleared.")

    async def on_timeout(self) -> None:
        await self._playback_service.stop_playback(self._guild_id)
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(
                    content=f"⏭️ Playback cleared (no response).", view=self
                )
            except discord.HTTPException:
                logger.debug("Failed to edit resume playback message on timeout")

    async def _finish(self, interaction: discord.Interaction, message: str) -> None:
        self.stop()
        self._disable_buttons()
        await interaction.response.edit_message(content=message, view=self)

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
