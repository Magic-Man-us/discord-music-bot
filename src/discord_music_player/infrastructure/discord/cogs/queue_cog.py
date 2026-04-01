"""Slash-command cog for queue management: view, shuffle, remove, clear, loop."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from ....domain.shared.constants import UIConstants

if TYPE_CHECKING:
    from discord_music_player.domain.music.entities import Track
from .base_cog import BaseCog
from ..guards.voice_guards import (
    ensure_dj_role,
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from ..services.embed_builder import format_requester
from ....utils.reply import deduplicate_tracks, format_duration, paginate, truncate


class QueueCog(BaseCog):
    @app_commands.command(
        name="queue", description="See what's playing now and what's coming up next."
    )
    @app_commands.guild_only()
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
            await interaction.response.send_message("Queue is empty.", ephemeral=True)
            return

        page, total_pages, start_idx = paginate(queue_info.total_tracks, page)

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

        tracks = queue_info.tracks[start_idx : start_idx + UIConstants.QUEUE_PER_PAGE]
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
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        shuffled = await queue_service.shuffle(interaction.guild.id)

        if shuffled:
            await interaction.response.send_message("Shuffled the queue.", ephemeral=True)
        else:
            await interaction.response.send_message("Not enough tracks to shuffle.", ephemeral=True)

    @app_commands.command(
        name="shuffle_history",
        description="Re-queue everything that's been played before, shuffled.",
    )
    @app_commands.guild_only()
    @app_commands.describe(limit="Max number of tracks to fetch (default: 100)")
    async def shuffle_history(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 500] = 100
    ) -> None:
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

        result = await self.enqueue_and_start(interaction, unique_tracks)

        await interaction.followup.send(
            f"Shuffled and queued **{result.enqueued}** tracks from history.",
            ephemeral=True,
        )

    @app_commands.command(
        name="shuffle_user_history",
        description="Re-queue a shuffled mix of tracks played by a specific user.",
    )
    @app_commands.guild_only()
    @app_commands.describe(
        user="The user whose history to shuffle",
        limit="Max number of tracks to fetch (default: 100)",
    )
    async def shuffle_user_history(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        limit: app_commands.Range[int, 1, 500] = 100,
    ) -> None:
        if not await ensure_voice(
            interaction, self.container.voice_warmup_tracker, self.container.voice_adapter
        ):
            return

        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        unique_tracks = await self._fetch_unique_user_history(interaction.guild.id, user.id, limit)
        if not unique_tracks:
            await interaction.followup.send(
                f"No tracks found in history for **{user.display_name}**.",
                ephemeral=True,
            )
            return

        import random

        random.shuffle(unique_tracks)

        result = await self.enqueue_and_start(interaction, unique_tracks)

        await interaction.followup.send(
            f"Shuffled and queued **{result.enqueued}** tracks from **{user.display_name}**'s history.",
            ephemeral=True,
        )

    async def _fetch_unique_user_history(
        self, guild_id: int, user_id: int, limit: int
    ) -> list[Track]:
        tracks = await self.container.history_repository.get_recent_by_user(
            guild_id, user_id, limit=limit
        )
        return deduplicate_tracks(tracks)

    async def _fetch_unique_history(self, guild_id: int, limit: int) -> list[Track]:
        tracks = await self.container.history_repository.get_recent(guild_id, limit=limit)
        return deduplicate_tracks(tracks)

    @app_commands.command(
        name="loop", description="Cycle loop mode: off → single track → whole queue."
    )
    @app_commands.guild_only()
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

    @app_commands.command(
        name="remove", description="Remove a specific track from the queue by its position number."
    )
    @app_commands.guild_only()
    @app_commands.describe(position="Position in queue (1-based)")
    async def remove(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
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

    @app_commands.command(
        name="move", description="Rearrange the queue — move a track from one position to another."
    )
    @app_commands.guild_only()
    @app_commands.describe(
        from_position="Current position (1-based)",
        to_position="Target position (1-based)",
    )
    async def move(
        self,
        interaction: discord.Interaction,
        from_position: app_commands.Range[int, 1],
        to_position: app_commands.Range[int, 1],
    ) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        success = await queue_service.move(interaction.guild.id, from_position - 1, to_position - 1)

        if success:
            await interaction.response.send_message(
                f"Moved track from position {from_position} to {to_position}.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Invalid position(s). Check the queue with `/queue`.",
                ephemeral=True,
            )

    @app_commands.command(
        name="clear",
        description="Remove all tracks from the queue (keeps the current song playing).",
    )
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        if not await ensure_dj_role(interaction, self.container.settings.discord.dj_role_id):
            return

        assert interaction.guild is not None

        queue_service = self.container.queue_service
        count = await queue_service.clear(interaction.guild.id)

        if count > 0:
            await self.container.message_state_manager.reset(interaction.guild.id)
            await interaction.response.send_message(
                f"Cleared {count} tracks from the queue.", ephemeral=True
            )
        else:
            await interaction.response.send_message("Queue is already empty.", ephemeral=True)


setup = QueueCog.setup
