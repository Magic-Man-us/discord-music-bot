"""Slash-command cog for queue management: view, shuffle, remove, clear, loop."""

from __future__ import annotations

import math

import discord
from discord import app_commands

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.domain.shared.types import DiscordSnowflake
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from discord_music_player.infrastructure.discord.services.embed_builder import format_requester
from discord_music_player.utils.reply import format_duration, truncate


class QueueCog(BaseCog):

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
                "Queue is empty.", ephemeral=True
            )
            return

        per_page = UIConstants.QUEUE_PER_PAGE
        total_pages = max(1, math.ceil(queue_info.total_tracks / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page

        embed = discord.Embed(
            title=f"Queue ({queue_info.total_tracks} tracks) — Page {page}/{total_pages}",
            color=discord.Color.blurple(),
        )

        if queue_info.current_track:
            ct = queue_info.current_track
            requester = format_requester(ct)
            artist_or_uploader = ct.artist or ct.uploader

            np_parts = [f"[{truncate(ct.title, UIConstants.TITLE_TRUNCATION)}]({ct.webpage_url})"]
            np_parts.append(f"Requested by: {requester}")
            if artist_or_uploader:
                np_parts.append(f"Artist: {truncate(artist_or_uploader, 64)}")
            np_parts.append(f"Duration: {format_duration(ct.duration_seconds)}")

            embed.add_field(
                name="Now Playing",
                value="\n".join(np_parts),
                inline=False,
            )

        tracks = queue_info.tracks[start_idx : start_idx + per_page]
        for idx, track in enumerate(tracks, start=start_idx + 1):
            embed.add_field(
                name=f"{idx}. {truncate(track.title)}",
                value=f"Requested by: {track.requested_by_name or UIConstants.UNKNOWN_FALLBACK}",
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
                "Shuffled the queue.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Not enough tracks to shuffle.", ephemeral=True
            )

    @app_commands.command(
        name="shuffle_history", description="Queue and shuffle all previously played tracks."
    )
    @app_commands.describe(limit="Max number of tracks to fetch (default: 100)")
    async def shuffle_history(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 500] = 100) -> None:
        if not await ensure_voice(
            interaction, self.container.voice_warmup_tracker, self.container.voice_adapter
        ):
            return

        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        unique_tracks = await self._fetch_unique_history(interaction.guild.id, limit)
        if not unique_tracks:
            await interaction.followup.send(
                "No tracks have been played yet in this server.", ephemeral=True
            )
            return

        import random

        random.shuffle(unique_tracks)

        enqueued_count, should_start = await self._enqueue_batch(
            interaction.guild.id, unique_tracks, interaction.user,
        )

        if should_start:
            await self.container.playback_service.start_playback(interaction.guild.id)

        await interaction.followup.send(
            f"Shuffled and queued **{enqueued_count}** tracks from history.",
            ephemeral=True,
        )

    async def _fetch_unique_history(self, guild_id: DiscordSnowflake, limit: int) -> list[Track]:
        """Fetch recent tracks and deduplicate by track ID."""
        tracks = await self.container.history_repository.get_recent(guild_id, limit=limit)
        seen: set[str] = set()
        unique: list[Track] = []
        for track in tracks:
            if track.id.value not in seen:
                seen.add(track.id.value)
                unique.append(track)
        return unique

    async def _enqueue_batch(
        self,
        guild_id: DiscordSnowflake,
        tracks: list[Track],
        user: discord.User | discord.Member,
    ) -> tuple[int, bool]:
        """Enqueue a list of tracks. Returns ``(count, should_start)``."""
        queue_service = self.container.queue_service
        count = 0
        should_start = False
        for track in tracks:
            result = await queue_service.enqueue(
                guild_id=guild_id,
                track=track,
                user_id=user.id,
                user_name=user.display_name,
            )
            if result.success:
                count += 1
                if result.should_start:
                    should_start = True
        return count, should_start

    @app_commands.command(name="loop", description="Toggle loop mode.")
    async def loop(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        mode = await queue_service.toggle_loop(interaction.guild.id)

        await interaction.response.send_message(
            f"Loop mode: **{mode.value}**",
            ephemeral=True,
        )

    @app_commands.command(name="remove", description="Remove a track from the queue.")
    @app_commands.describe(position="Position in queue (1-based)")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1]) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        track = await queue_service.remove(interaction.guild.id, position - 1)

        if track:
            await interaction.response.send_message(
                f"Removed: **{track.title}**",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"No track at position {position}.",
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
                f"Cleared {count} tracks from the queue.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Queue is already empty.", ephemeral=True
            )


setup = QueueCog.setup
