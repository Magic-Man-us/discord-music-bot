"""View prompting users to resume playback after bot restart."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.constants import UIConstants
from ....domain.shared.types import DiscordSnowflake
from ....utils.logging import get_logger
from ....utils.reply import format_duration
from ..guards.voice_guards import check_user_in_voice
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....application.services.playback_service import PlaybackApplicationService
    from ....domain.music.wrappers import StartSeconds

logger = get_logger(__name__)

_DELETE_AFTER = UIConstants.FINISHED_DELETE_AFTER


class ResumePlaybackView(BaseInteractiveView):
    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        channel_id: DiscordSnowflake,
        playback_service: PlaybackApplicationService,
        track_title: str,
        resume_start_seconds: StartSeconds | None = None,
    ) -> None:
        super().__init__(timeout=30.0)
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._playback_service = playback_service
        self._track_title = track_title
        self._resume_start_seconds = resume_start_seconds

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.green)
    async def resume_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        if not self._finish_view():
            return

        timestamp = ""
        if self._resume_start_seconds is not None:
            timestamp = f" from {format_duration(self._resume_start_seconds.value)}"

        msg = f"Resumed playback: **{self._track_title}**{timestamp}"
        await self._playback_service.start_playback(
            self._guild_id,
            start_seconds=self._resume_start_seconds,
        )
        await interaction.response.edit_message(content=msg, embed=None, view=None)
        await self._delete_message(delay=_DELETE_AFTER)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.red)
    async def skip_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[ResumePlaybackView]
    ) -> None:
        if not self._finish_view():
            return
        await self._playback_service.stop_playback(self._guild_id)
        await interaction.response.edit_message(
            content="Skipped. Playback cleared.",
            embed=None,
            view=None,
        )
        await self._delete_message(delay=_DELETE_AFTER)

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        await self._playback_service.stop_playback(self._guild_id)
        await self._delete_message(delay=10.0)
