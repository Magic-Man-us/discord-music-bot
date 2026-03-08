"""Slash-command cog for AI radio functionality."""

from __future__ import annotations

import asyncio
import logging
import discord
from discord import app_commands
from discord.ext import commands

from typing import TYPE_CHECKING

from discord_music_player.domain.shared.enums import RadioAction
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
)

if TYPE_CHECKING:
    from discord_music_player.application.services.radio_models import RadioToggleResult

logger = logging.getLogger(__name__)


class RadioCog(BaseCog):

    @app_commands.command(
        name="radio",
        description="Toggle AI radio \u2014 auto-queue similar songs.",
    )
    @app_commands.describe(
        query="Optional: song name or URL to seed radio with",
        action="Action to perform (default: toggle)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Toggle radio on/off", value="toggle"),
            app_commands.Choice(name="Clear AI recommendations from queue", value="clear"),
        ]
    )
    async def radio(
        self,
        interaction: discord.Interaction,
        query: str | None = None,
        action: app_commands.Choice[str] | None = None,
    ) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        action_value = action.value if action else RadioAction.TOGGLE
        if action_value == RadioAction.CLEAR:
            await self._handle_clear(interaction)
            return

        await self._handle_toggle(interaction, query)

    async def _handle_clear(self, interaction: discord.Interaction) -> None:
        """Disable radio and clear AI recommendations from the queue."""
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        self.container.radio_service.disable_radio(interaction.guild.id)
        count = await self.container.queue_service.clear_recommendations(interaction.guild.id)

        msg = (
            f"📻 Radio disabled. Removed **{count}** AI recommendation(s) from the queue."
            if count > 0
            else "📻 Radio disabled. No AI recommendations were in the queue."
        )
        await interaction.followup.send(msg, ephemeral=True)

    async def _handle_toggle(
        self, interaction: discord.Interaction, query: str | None,
    ) -> None:
        """Toggle or seed radio, then display the result."""
        assert interaction.guild is not None
        await interaction.response.defer()

        guild_id = interaction.guild.id
        user = interaction.user
        radio_service = self.container.radio_service

        if query:
            await self._seed_and_enable(interaction, query)

        result = await radio_service.toggle_radio(
            guild_id=guild_id,
            user_id=user.id,
            user_name=user.display_name,
        )

        if not result.enabled:
            msg = f"{"📻 Radio disabled."} {result.message}" if result.message else "📻 Radio disabled."
            await interaction.followup.send(msg, ephemeral=True)
            return

        await self._send_radio_enabled(interaction, result)

    async def _seed_and_enable(
        self, interaction: discord.Interaction, query: str,
    ) -> None:
        """Play a seed track and reset radio state so toggle_radio enables fresh."""
        assert interaction.guild is not None
        guild_id = interaction.guild.id
        radio_service = self.container.radio_service

        playback_cog = self.bot.get_cog("PlaybackCog")
        if playback_cog is not None:
            await playback_cog._execute_play(interaction, query)  # type: ignore[attr-defined]
        await asyncio.sleep(0.5)

        # Disable first if already enabled, then toggle_radio will re-enable
        if radio_service.is_enabled(guild_id):
            radio_service.disable_radio(guild_id)

    async def _send_radio_enabled(
        self, interaction: discord.Interaction, result: RadioToggleResult,
    ) -> None:
        """Send the 'Up Next' embed with per-track re-roll buttons."""
        assert interaction.guild is not None
        from ..views.radio_view import RadioView, build_up_next_embed

        queue_info = await self.container.queue_service.get_queue(interaction.guild.id)
        queue_start = max(0, queue_info.total_length - len(result.generated_tracks))

        embed = build_up_next_embed(result.generated_tracks, result.seed_title)
        view = RadioView(
            guild_id=interaction.guild.id,
            container=self.container,
            tracks=result.generated_tracks,
            seed_title=result.seed_title,
            queue_start_position=queue_start,
        )
        msg = await interaction.followup.send(embed=embed, view=view, wait=True)
        view._message = msg


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError("Container not found on bot instance")

    await bot.add_cog(RadioCog(bot, container))
