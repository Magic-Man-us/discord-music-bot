"""Slash-command cog for AI radio functionality."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from discord_music_player.domain.shared.enums import RadioAction
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)

if TYPE_CHECKING:
    from discord_music_player.application.services.radio_models import RadioToggleResult


class RadioCog(BaseCog):

    @app_commands.command(
        name="radio",
        description="Toggle AI radio — auto-queue similar songs.",
    )
    @app_commands.describe(
        query="Optional: song name or URL to seed radio with",
        action="Action to perform (default: toggle)",
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Toggle radio on/off", value=RadioAction.TOGGLE),
            app_commands.Choice(name="Clear AI recommendations from queue", value=RadioAction.CLEAR),
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

        radio_action = RadioAction(action.value) if action else RadioAction.TOGGLE
        if radio_action is RadioAction.CLEAR:
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
            f"Radio disabled. Removed **{count}** AI recommendation(s) from the queue."
            if count > 0
            else "Radio disabled. No AI recommendations were in the queue."
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
            seeded = await self._seed_track(interaction, query)
            if not seeded:
                return

        result = await radio_service.toggle_radio(
            guild_id=guild_id,
            user_id=user.id,
            user_name=user.display_name,
        )

        if not result.enabled:
            msg = f"Radio disabled. {result.message}" if result.message else "Radio disabled."
            await interaction.followup.send(msg, ephemeral=True)
            return

        await self._send_radio_enabled(interaction, result)

    async def _seed_track(
        self, interaction: discord.Interaction, query: str,
    ) -> bool:
        """Resolve and enqueue a seed track directly. Returns True on success."""
        assert interaction.guild is not None
        guild_id = interaction.guild.id

        # Ensure bot is connected to voice
        if not await ensure_voice(
            interaction,
            self.container.voice_warmup_tracker,
            self.container.voice_adapter,
        ):
            return False

        track = await self.container.audio_resolver.resolve(query)
        if not track:
            await interaction.followup.send(
                f"Couldn't find a track for: {query}", ephemeral=True
            )
            return False

        result = await self.container.queue_service.enqueue(
            guild_id=guild_id,
            track=track,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if not result.success:
            await interaction.followup.send(result.message, ephemeral=True)
            return False

        if result.should_start:
            await self.container.playback_service.start_playback(guild_id)

        # Disable existing radio so toggle_radio re-enables fresh
        radio_service = self.container.radio_service
        if radio_service.is_enabled(guild_id):
            radio_service.disable_radio(guild_id)

        return True

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
        view.set_message(msg)


setup = RadioCog.setup
