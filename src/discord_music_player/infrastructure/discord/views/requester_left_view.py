"""View prompting listeners to continue or skip when the requester leaves."""

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


class RequesterLeftView(BaseInteractiveView):
    def __init__(
        self,
        *,
        guild_id: int,
        playback_service: PlaybackApplicationService,
        track_title: str,
        requester_name: str,
    ) -> None:
        super().__init__(timeout=30.0)
        self._guild_id = guild_id
        self._playback_service = playback_service
        self._track_title = track_title
        self._requester_name = requester_name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Yes, continue", style=discord.ButtonStyle.green)
    async def yes_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[RequesterLeftView]
    ) -> None:
        await self._playback_service.resume_playback(self._guild_id)
        await self._finish(interaction, DiscordUIMessages.REQUESTER_LEFT_RESUMED)

    @discord.ui.button(label="No, skip", style=discord.ButtonStyle.red)
    async def no_button(
        self, interaction: discord.Interaction, button: discord.ui.Button[RequesterLeftView]
    ) -> None:
        await self._playback_service.skip_track(self._guild_id)
        await self._finish(interaction, DiscordUIMessages.REQUESTER_LEFT_SKIPPED)

    async def on_timeout(self) -> None:
        await self._playback_service.skip_track(self._guild_id)
        self._disable_buttons()
        if self._message is not None:
            try:
                await self._message.edit(
                    content=DiscordUIMessages.REQUESTER_LEFT_TIMEOUT, view=self
                )
            except discord.HTTPException:
                logger.debug("Failed to edit requester-left message on timeout")

    async def _finish(self, interaction: discord.Interaction, message: str) -> None:
        self.stop()
        self._disable_buttons()
        await interaction.response.edit_message(content=message, view=self)
