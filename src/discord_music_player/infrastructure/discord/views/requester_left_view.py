"""View prompting listeners to continue or skip when the requester leaves."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ....domain.shared.types import DiscordSnowflake
from ....utils.logging import get_logger
from ..guards.voice_guards import check_user_in_voice
from .base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....application.services.playback_service import PlaybackApplicationService
    from ....application.services.requester_leave_autoskip import AutoSkipOnRequesterLeave

logger = get_logger(__name__)


class RequesterLeftView(BaseInteractiveView):
    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        playback_service: PlaybackApplicationService,
        auto_skip_service: AutoSkipOnRequesterLeave,
        track_title: str,
        requester_name: str,
    ) -> None:
        super().__init__(timeout=30.0)
        self._guild_id = guild_id
        self._playback_service = playback_service
        self._auto_skip_service = auto_skip_service
        self._track_title = track_title
        self._requester_name = requester_name

    def _resolve(self) -> bool:
        """Mark view as finished and clear the pending requester-left state."""
        if not self._finish_view():
            return False
        self._auto_skip_service.clear_pending(self._guild_id)
        return True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Yes, continue", style=discord.ButtonStyle.green)
    async def yes_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[RequesterLeftView]
    ) -> None:
        if not self._resolve():
            return
        await self._playback_service.resume_playback(self._guild_id)
        await interaction.response.edit_message(content="Playback resumed.", view=self)

    @discord.ui.button(label="No, skip", style=discord.ButtonStyle.red)
    async def no_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[RequesterLeftView]
    ) -> None:
        if not self._resolve():
            return
        await self._playback_service.skip_track(self._guild_id)
        await interaction.response.edit_message(content="Track skipped.", view=self)

    async def on_timeout(self) -> None:
        if not self._resolve():
            return
        await self._playback_service.skip_track(self._guild_id)
        await self._delete_message(delay=10.0)

    async def dismiss(self, message: str = "Requester rejoined — playback resumed.") -> None:
        """Externally dismiss this view (e.g. when the requester rejoins)."""
        if not self._finish_view():
            return
        if self._message is not None:
            try:
                await self._message.edit(content=message, view=self)
            except discord.HTTPException:
                pass
        await self._delete_message(delay=10.0)
