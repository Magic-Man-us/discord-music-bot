"""View prompting users to resume playback after bot restart."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.infrastructure.discord.views.base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....application.services.playback_service import PlaybackApplicationService

logger = logging.getLogger(__name__)


class ResumePlaybackView(BaseInteractiveView):
    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        channel_id: DiscordSnowflake,
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

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green)
    async def resume_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        msg = f"Resumed playback: **{self._track_title}**"
        if not self._finish_view():
            return
        await self._playback_service.start_playback(self._guild_id)
        await interaction.response.edit_message(content=msg, view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red)
    async def skip_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        if not self._finish_view():
            return
        await self._playback_service.stop_playback(self._guild_id)
        await interaction.response.edit_message(
            content="Skipped. Playback cleared.", view=self
        )

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        await self._playback_service.stop_playback(self._guild_id)
        await self._delete_message(delay=10.0)
