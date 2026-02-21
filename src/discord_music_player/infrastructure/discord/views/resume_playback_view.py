"""View prompting users to resume playback after bot restart."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.infrastructure.discord.views.base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....application.services.playback_service import PlaybackApplicationService

logger = logging.getLogger(__name__)


class ResumePlaybackView(BaseInteractiveView):
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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.green)
    async def resume_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        await self._playback_service.start_playback(self._guild_id)
        await self._finish(
            interaction,
            DiscordUIMessages.RESUME_PLAYBACK_RESUMED.format(track_title=self._track_title),
        )

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.red)
    async def skip_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        await self._playback_service.stop_playback(self._guild_id)
        await self._finish(interaction, DiscordUIMessages.RESUME_PLAYBACK_CLEARED)

    async def on_timeout(self) -> None:
        await self._playback_service.stop_playback(self._guild_id)
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(
                    content=DiscordUIMessages.RESUME_PLAYBACK_TIMEOUT, view=self
                )
            except discord.HTTPException:
                logger.debug("Failed to edit resume playback message on timeout")

    async def _finish(self, interaction: discord.Interaction, message: str) -> None:
        self.stop()
        self._disable_buttons()
        await interaction.response.edit_message(content=message, view=self)
