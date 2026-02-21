"""Slash-command cog for viewing current track and play history."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    send_ephemeral,
)
from discord_music_player.infrastructure.discord.services.message_state_manager import (
    MessageStateManager,
)
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)


class NowPlayingCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

    @app_commands.command(name="current", description="Show the current track.")
    async def current(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        queue_info = await queue_service.get_queue(interaction.guild.id)

        if not queue_info.current_track:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOTHING_PLAYING, ephemeral=True
            )
            return

        track = queue_info.current_track
        upcoming = queue_info.tracks[0] if queue_info.tracks else None

        embed = MessageStateManager.build_now_playing_embed(track, next_track=upcoming)

        from ..views.now_playing_view import NowPlayingView

        view = NowPlayingView(
            webpage_url=track.webpage_url,
            title=track.title,
            guild_id=interaction.guild.id,
            container=self.container,
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        try:
            msg = await interaction.original_response()
            view.set_message(msg)
        except discord.HTTPException:
            pass

    @app_commands.command(
        name="played",
        description="Show recently played tracks for this server.",
    )
    async def played(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        if not interaction.guild:
            return

        history_repo = self.container.history_repository
        tracks = await history_repo.get_recent(interaction.guild.id, limit=10)
        if not tracks:
            await send_ephemeral(interaction, DiscordUIMessages.STATE_NO_TRACKS_PLAYED_YET)
            return

        lines: list[str] = []
        for index, history_track in enumerate(tracks, start=1):
            parts: list[str] = []

            title = truncate(history_track.title, 80)
            parts.append(f"**{index}.** [{title}]({history_track.webpage_url})")

            artist_or_uploader = history_track.artist or history_track.uploader
            if artist_or_uploader:
                parts.append(truncate(artist_or_uploader, 48))

            duration = format_duration(history_track.duration_seconds)
            if duration:
                parts.append(duration)

            if history_track.like_count is not None:
                parts.append(f"\U0001f44d {history_track.like_count:,}")

            if history_track.requested_by_id:
                parts.append(f"req <@{history_track.requested_by_id}>")
            elif history_track.requested_by_name:
                parts.append(f"req {truncate(history_track.requested_by_name, 24)}")

            lines.append(" \u2014 ".join(parts))

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_RECENTLY_PLAYED,
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError("Container not found on bot instance")

    await bot.add_cog(NowPlayingCog(bot, container))
