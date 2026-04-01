"""'Continue Radio?' prompt shown when the recommendation pool is exhausted."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.guards.voice_guards import check_user_in_voice
from discord_music_player.infrastructure.discord.views.base_view import BaseInteractiveView

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)

_CONTINUE_TIMEOUT: float = 120.0
_RADIO_STOPPED_TITLE: str = "Radio Stopped"


def build_continue_embed(tracks_consumed: int) -> discord.Embed:
    return discord.Embed(
        title="Radio Batch Complete",
        description=(
            f"**{tracks_consumed}** tracks played so far.\n\n"
            "Want to continue with more recommendations?"
        ),
        color=discord.Color.purple(),
    )


class RadioContinueView(BaseInteractiveView):
    def __init__(
        self,
        *,
        guild_id: DiscordSnowflake,
        container: Container,
    ) -> None:
        super().__init__(timeout=_CONTINUE_TIMEOUT)
        self._guild_id = guild_id
        self._container = container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_user_in_voice(interaction, self._guild_id)

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.success)
    async def continue_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[RadioContinueView],
    ) -> None:
        if not self._finish_view():
            return

        await interaction.response.defer()

        radio_service = self._container.radio_service
        result = await radio_service.continue_radio(self._guild_id)

        if not result.enabled:
            msg = result.message or "Couldn't continue radio."
            embed = discord.Embed(
                title=_RADIO_STOPPED_TITLE,
                description=msg,
                color=discord.Color.greyple(),
            )
            await interaction.edit_original_response(embed=embed, view=self)
            return

        from ..views.radio_view import RadioView, build_up_next_embed

        queue_info = await self._container.queue_service.get_queue(self._guild_id)
        queue_start = max(0, queue_info.total_tracks - len(result.generated_tracks))

        embed = build_up_next_embed(result.generated_tracks, result.seed_title)
        embed.set_footer(text="Radio continued — new batch loaded")
        view = RadioView(
            guild_id=self._guild_id,
            container=self._container,
            tracks=result.generated_tracks,
            seed_title=result.seed_title,
            queue_start_position=queue_start,
        )
        msg_obj = await interaction.edit_original_response(embed=embed, view=view)
        view.set_message(msg_obj)

        if result.generated_tracks:
            session = await self._container.session_repository.get(self._guild_id)
            if session is not None and session.is_idle:
                await self._container.playback_service.start_playback(self._guild_id)

    @discord.ui.button(label="Stop Radio", style=discord.ButtonStyle.danger)
    async def stop_button(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button[RadioContinueView],
    ) -> None:
        if not self._finish_view():
            return

        self._container.radio_service.disable_radio(self._guild_id)

        embed = discord.Embed(
            title=_RADIO_STOPPED_TITLE,
            description="Radio has been disabled.",
            color=discord.Color.greyple(),
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return

        self._container.radio_service.disable_radio(self._guild_id)
        await self._delete_message(delay=10.0)
