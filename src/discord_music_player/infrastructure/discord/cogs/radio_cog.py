"""Slash-command cog for AI radio functionality."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.shared.enums import RadioAction
from discord_music_player.domain.shared.messages import DiscordUIMessages, ErrorMessages
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
)
from discord_music_player.utils.reply import truncate

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class RadioCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

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

        # Handle "clear" action
        action_value = action.value if action else RadioAction.TOGGLE
        if action_value == RadioAction.CLEAR:
            await interaction.response.defer(ephemeral=True)
            radio_service = self.container.radio_service
            queue_service = self.container.queue_service

            # Disable radio
            radio_service.disable_radio(interaction.guild.id)

            # Clear AI recommendations from queue
            count = await queue_service.clear_recommendations(interaction.guild.id)

            if count > 0:
                await interaction.followup.send(
                    DiscordUIMessages.RADIO_CLEARED_WITH_COUNT.format(count=count),
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    DiscordUIMessages.RADIO_CLEARED_EMPTY,
                    ephemeral=True,
                )
            return

        # Normal toggle/enable flow
        await interaction.response.defer()

        user = interaction.user

        radio_service = self.container.radio_service

        # If query provided, play it first, then force-enable radio (don't toggle)
        if query:
            playback_cog = self.bot.get_cog("PlaybackCog")
            if playback_cog is not None:
                await playback_cog._execute_play(interaction, query)  # type: ignore[attr-defined]
            # Wait a moment for the track to start
            await asyncio.sleep(0.5)

            # Disable first if already enabled, then enable fresh
            if radio_service.is_enabled(interaction.guild.id):
                radio_service.disable_radio(interaction.guild.id)

            result = await radio_service.toggle_radio(
                guild_id=interaction.guild.id,
                user_id=user.id,
                user_name=getattr(user, "display_name", user.name),
            )
        else:
            # No query - normal toggle behavior
            result = await radio_service.toggle_radio(
                guild_id=interaction.guild.id,
                user_id=user.id,
                user_name=getattr(user, "display_name", user.name),
            )

        # If disabling radio or error, send ephemeral message
        if not result.enabled:
            if result.message:
                msg = f"{DiscordUIMessages.RADIO_DISABLED} {result.message}"
            else:
                msg = DiscordUIMessages.RADIO_DISABLED
            await interaction.followup.send(msg, ephemeral=True)
            return

        # Radio enabled - send public message with "Up Next" and shuffle button
        queue_service = self.container.queue_service
        queue_info = await queue_service.get_queue(interaction.guild.id)

        embed = discord.Embed(
            title="\U0001f4fb Radio Enabled",
            description=f"Playing similar tracks based on **{result.seed_title}**",
            color=discord.Color.purple(),
        )

        # Show "Up Next" section with queued tracks
        if queue_info.tracks:
            up_next_lines = []
            for idx, track in enumerate(queue_info.tracks[:result.tracks_added], start=1):
                title = truncate(track.title, 60)
                up_next_lines.append(f"{idx}. {title}")

            embed.add_field(
                name="\U0001f3b5 Up Next",
                value="\n".join(up_next_lines) if up_next_lines else "No tracks queued",
                inline=False,
            )

        from ..views.radio_view import RadioView

        view = RadioView(guild_id=interaction.guild.id, container=self.container)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError(ErrorMessages.CONTAINER_NOT_FOUND)

    await bot.add_cog(RadioCog(bot, container))
