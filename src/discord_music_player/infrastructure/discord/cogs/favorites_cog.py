"""Slash-command cog for user favorites: save, list, play, remove."""

from __future__ import annotations

import discord
from discord import app_commands

from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from discord_music_player.utils.reply import format_duration, truncate

_FAVORITES_PER_PAGE = UIConstants.QUEUE_PER_PAGE


class FavoritesCog(BaseCog):

    favorites = app_commands.Group(name="favorites", description="Manage your favorite tracks")

    @favorites.command(name="add", description="Save the currently playing track to your favorites.")
    async def favorites_add(self, interaction: discord.Interaction) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        session = await self.container.session_repository.get(interaction.guild.id)
        if session is None or session.current_track is None:
            await interaction.response.send_message(
                "Nothing is playing right now.", ephemeral=True
            )
            return

        track = session.current_track
        repo = self.container.favorites_repository
        added = await repo.add(interaction.user.id, track)

        if added:
            title = truncate(track.title, UIConstants.TITLE_TRUNCATION)
            await interaction.response.send_message(
                f"Saved **{title}** to your favorites.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Track is already in your favorites or you've reached the limit.",
                ephemeral=True,
            )

    @favorites.command(name="list", description="Show your saved favorite tracks.")
    @app_commands.describe(page="Page number")
    async def favorites_list(self, interaction: discord.Interaction, page: int = 1) -> None:
        repo = self.container.favorites_repository
        tracks = await repo.get_all(interaction.user.id)

        if not tracks:
            await interaction.response.send_message(
                "You don't have any favorites yet. Use `/favorites add` while a track is playing.",
                ephemeral=True,
            )
            return

        total_pages = max(1, -(-len(tracks) // _FAVORITES_PER_PAGE))
        page = max(1, min(page, total_pages))
        start = (page - 1) * _FAVORITES_PER_PAGE

        embed = discord.Embed(
            title=f"Your Favorites ({len(tracks)} tracks) — Page {page}/{total_pages}",
            color=discord.Color.gold(),
        )

        page_tracks = tracks[start : start + _FAVORITES_PER_PAGE]
        for idx, track in enumerate(page_tracks, start=start + 1):
            duration = format_duration(track.duration_seconds) if track.duration_seconds else "?"
            artist = track.artist or track.uploader or ""
            value = f"[{truncate(track.title, 60)}]({track.webpage_url})"
            if artist:
                value += f" — {truncate(artist, 40)}"
            value += f" [{duration}]"
            embed.add_field(name=f"{idx}.", value=value, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @favorites.command(name="play", description="Queue all your favorites (shuffled).")
    async def favorites_play(self, interaction: discord.Interaction) -> None:
        if not await ensure_voice(
            interaction, self.container.voice_warmup_tracker, self.container.voice_adapter
        ):
            return

        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        repo = self.container.favorites_repository
        tracks = await repo.get_all(interaction.user.id)

        if not tracks:
            await interaction.followup.send(
                "You don't have any favorites yet.", ephemeral=True
            )
            return

        import random

        random.shuffle(tracks)

        result = await self.container.queue_service.enqueue_batch(
            guild_id=interaction.guild.id,
            tracks=tracks,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if result.should_start:
            await self.container.playback_service.start_playback(interaction.guild.id)

        await interaction.followup.send(
            f"Shuffled and queued **{result.enqueued}** favorites.", ephemeral=True
        )

    @favorites.command(name="remove", description="Remove a track from your favorites by position.")
    @app_commands.describe(position="Position in your favorites list (1-based)")
    async def favorites_remove(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        repo = self.container.favorites_repository
        tracks = await repo.get_all(interaction.user.id)

        if position > len(tracks):
            await interaction.response.send_message(
                f"Invalid position. You have {len(tracks)} favorites.",
                ephemeral=True,
            )
            return

        track = tracks[position - 1]
        track_id_str = track.id.value if hasattr(track.id, "value") else str(track.id)
        removed = await repo.remove(interaction.user.id, track_id_str)

        if removed:
            title = truncate(track.title, UIConstants.TITLE_TRUNCATION)
            await interaction.response.send_message(
                f"Removed **{title}** from your favorites.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Could not remove that track.", ephemeral=True
            )


setup = FavoritesCog.setup
