"""Slash commands for saving and loading named queue playlists."""

from __future__ import annotations

import random

import discord
from discord import app_commands

from discord_music_player.domain.shared.constants import UIConstants
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    ensure_voice,
)
from discord_music_player.utils.reply import format_duration, truncate


class SavedQueueCog(BaseCog):

    saved = app_commands.Group(
        name="playlist", description="Save and load named queue playlists."
    )

    @saved.command(name="save", description="Save the current queue as a named playlist.")
    @app_commands.describe(name="Playlist name")
    async def save_queue(self, interaction: discord.Interaction, name: str) -> None:
        if not await ensure_user_in_voice_and_warm(
            interaction, self.container.voice_warmup_tracker
        ):
            return

        assert interaction.guild is not None

        session = await self.container.session_repository.get(interaction.guild.id)
        if session is None or not session.has_tracks:
            await interaction.response.send_message(
                "Nothing to save — the queue is empty.", ephemeral=True
            )
            return

        tracks = list(session.queue)
        if session.current_track:
            tracks.insert(0, session.current_track)

        repo = self.container.saved_queue_repository
        success = await repo.save(
            guild_id=interaction.guild.id,
            name=name.strip().lower(),
            tracks=tracks,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if success:
            await interaction.response.send_message(
                f"Saved **{len(tracks)}** tracks as **{name}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "Too many saved playlists. Delete one first with `/playlist delete`.",
                ephemeral=True,
            )

    @saved.command(name="load", description="Load a saved playlist into the queue.")
    @app_commands.describe(
        name="Playlist name",
        shuffle="Shuffle tracks before loading",
    )
    async def load_queue(
        self,
        interaction: discord.Interaction,
        name: str,
        shuffle: bool = False,
    ) -> None:
        if not await ensure_voice(
            interaction, self.container.voice_warmup_tracker, self.container.voice_adapter
        ):
            return

        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        repo = self.container.saved_queue_repository
        saved = await repo.get(interaction.guild.id, name.strip().lower())
        if saved is None:
            await interaction.followup.send(
                f"No playlist named **{name}** found. Use `/playlist list` to see available ones.",
                ephemeral=True,
            )
            return

        tracks = saved.to_tracks()
        if shuffle:
            random.shuffle(tracks)

        result = await self.container.queue_service.enqueue_batch(
            guild_id=interaction.guild.id,
            tracks=tracks,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )

        if result.should_start:
            await self.container.playback_service.start_playback(interaction.guild.id)

        shuffle_label = " (shuffled)" if shuffle else ""
        await interaction.followup.send(
            f"Loaded **{result.enqueued}** tracks from **{name}**{shuffle_label}.",
            ephemeral=True,
        )

    @saved.command(name="list", description="List all saved playlists for this server.")
    async def list_queues(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None

        repo = self.container.saved_queue_repository
        queues = await repo.list_all(interaction.guild.id)

        if not queues:
            await interaction.response.send_message(
                "No saved playlists. Use `/playlist save` to create one.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Saved Playlists ({len(queues)})",
            color=discord.Color.blurple(),
        )

        for q in queues:
            embed.add_field(
                name=q.name,
                value=f"{q.track_count} tracks — by {q.created_by_name}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @saved.command(name="delete", description="Delete a saved playlist.")
    @app_commands.describe(name="Playlist name to delete")
    async def delete_queue(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None

        repo = self.container.saved_queue_repository
        deleted = await repo.delete(interaction.guild.id, name.strip().lower())

        if deleted:
            await interaction.response.send_message(
                f"Deleted playlist **{name}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"No playlist named **{name}** found.", ephemeral=True
            )


setup = SavedQueueCog.setup
