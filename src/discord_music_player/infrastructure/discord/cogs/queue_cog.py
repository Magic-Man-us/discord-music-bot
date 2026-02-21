"""Slash-command cog for queue management: view, shuffle, remove, clear, loop."""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.music.value_objects import LoopMode
from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from discord_music_player.utils.reply import format_duration, truncate

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)

QUEUE_PER_PAGE = 10


class QueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container

    @app_commands.command(name="queue", description="Show the current queue.")
    @app_commands.describe(page="Page number")
    async def queue(self, interaction: discord.Interaction, page: int = 1) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        queue_info = await queue_service.get_queue(interaction.guild.id)

        if queue_info.total_tracks == 0:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_QUEUE_EMPTY, ephemeral=True
            )
            return

        per_page = QUEUE_PER_PAGE
        total_pages = max(1, math.ceil(queue_info.total_tracks / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_QUEUE.format(
                total_tracks=queue_info.total_tracks, page=page, total_pages=total_pages
            ),
            color=discord.Color.blurple(),
        )

        if queue_info.current_track:
            embed.add_field(
                name="\U0001f3b5 Now Playing",
                value=f"**{truncate(queue_info.current_track.title)}**\n"
                f"Duration: {format_duration(queue_info.current_track.duration_seconds)}",
                inline=False,
            )

        tracks = queue_info.tracks[start_idx : start_idx + per_page]
        for idx, track in enumerate(tracks, start=start_idx + 1):
            embed.add_field(
                name=f"{idx}. {truncate(track.title)}",
                value=f"Requested by: {track.requested_by_name or 'Unknown'}",
                inline=False,
            )

        if queue_info.total_duration:
            embed.set_footer(text=f"Total duration: {format_duration(queue_info.total_duration)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffle the queue.")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        shuffled = await queue_service.shuffle(interaction.guild.id)

        if shuffled:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_SHUFFLED, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_NOT_ENOUGH_TRACKS_TO_SHUFFLE, ephemeral=True
            )

    @app_commands.command(
        name="shuffle_history", description="Queue and shuffle all previously played tracks."
    )
    @app_commands.describe(limit="Max number of tracks to fetch (default: 100)")
    async def shuffle_history(self, interaction: discord.Interaction, limit: int = 100) -> None:
        if not await ensure_voice(
            interaction, self.container.voice_warmup_tracker, self.container.voice_adapter
        ):
            return

        assert interaction.guild is not None

        await interaction.response.defer(ephemeral=True)

        history_repo = self.container.history_repository
        queue_service = self.container.queue_service
        playback_service = self.container.playback_service
        user = interaction.user

        # Fetch recent history
        history_tracks = await history_repo.get_recent(interaction.guild.id, limit=limit)
        if not history_tracks:
            await interaction.followup.send(
                DiscordUIMessages.STATE_NO_TRACKS_PLAYED_YET, ephemeral=True
            )
            return

        # Dedupe by track_id using a set
        seen_ids: set[str] = set()
        unique_tracks = []
        for track in history_tracks:
            if track.id.value not in seen_ids:
                seen_ids.add(track.id.value)
                unique_tracks.append(track)

        if not unique_tracks:
            await interaction.followup.send(
                DiscordUIMessages.STATE_NO_TRACKS_PLAYED_YET, ephemeral=True
            )
            return

        # Shuffle the unique tracks
        import random

        random.shuffle(unique_tracks)

        # Enqueue all tracks
        enqueued_count = 0
        should_start = False
        for track in unique_tracks:
            result = await queue_service.enqueue(
                guild_id=interaction.guild.id,
                track=track,
                user_id=user.id,
                user_name=getattr(user, "display_name", user.name),
            )
            if result.success:
                enqueued_count += 1
                if result.should_start:
                    should_start = True

        # Start playback if needed
        if should_start:
            await playback_service.start_playback(interaction.guild.id)

        await interaction.followup.send(
            f"\U0001f500 Shuffled and queued **{enqueued_count}** tracks from history.",
            ephemeral=True,
        )

    @app_commands.command(name="loop", description="Toggle loop mode.")
    async def loop(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        mode = await queue_service.toggle_loop(interaction.guild.id)

        match mode:
            case LoopMode.OFF:
                emoji = "\u27a1\ufe0f"
            case LoopMode.TRACK:
                emoji = "\U0001f502"
            case LoopMode.QUEUE:
                emoji = "\U0001f501"
            case _:
                emoji = "\u27a1\ufe0f"

        await interaction.response.send_message(
            DiscordUIMessages.ACTION_LOOP_MODE_CHANGED.format(emoji=emoji, mode=mode.value),
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Remove a track from the queue.")
    @app_commands.describe(position="Position in queue (1-based)")
    async def remove(self, interaction: discord.Interaction, position: int) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        if position < 1:
            await interaction.response.send_message(
                DiscordUIMessages.ERROR_POSITION_MUST_BE_POSITIVE, ephemeral=True
            )
            return

        queue_service = self.container.queue_service
        track = await queue_service.remove(interaction.guild.id, position - 1)

        if track:
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_TRACK_REMOVED.format(track_title=track.title),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.ERROR_NO_TRACK_AT_POSITION.format(position=position),
                ephemeral=True,
            )

    @app_commands.command(name="clear", description="Clear the queue.")
    async def clear(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        count = await queue_service.clear(interaction.guild.id)

        if count > 0:
            self.container.message_state_manager.reset(interaction.guild.id)
            await interaction.response.send_message(
                DiscordUIMessages.ACTION_QUEUE_CLEARED.format(count=count), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                DiscordUIMessages.STATE_QUEUE_ALREADY_EMPTY, ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    container = getattr(bot, "container", None)
    if container is None:
        raise RuntimeError("Container not found on bot instance")

    await bot.add_cog(QueueCog(bot, container))
