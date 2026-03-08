"""Slash-command cog for viewing current track and play history."""

from __future__ import annotations

import discord
from discord import app_commands

from discord_music_player.domain.shared.constants import AnalyticsConstants, UIConstants
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.infrastructure.discord.guards.voice_guards import (
    ensure_user_in_voice_and_warm,
    send_ephemeral,
)
from discord_music_player.infrastructure.discord.services.embed_builder import (
    build_now_playing_embed,
)
from discord_music_player.utils.reply import format_duration, truncate


class NowPlayingCog(BaseCog):
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
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return

        track = queue_info.current_track
        upcoming = queue_info.tracks[0] if queue_info.tracks else None

        embed = build_now_playing_embed(track, next_track=upcoming)

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
        tracks = await history_repo.get_recent(
            interaction.guild.id, limit=AnalyticsConstants.DEFAULT_LEADERBOARD_LIMIT
        )
        if not tracks:
            await send_ephemeral(interaction, "No tracks have been played yet in this server.")
            return

        lines = [self._format_history_line(i, t) for i, t in enumerate(tracks, start=1)]
        embed = discord.Embed(
            title="Recently Played",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    def _format_history_line(index: int, track: object) -> str:
        """Format a single track's history line for the /played embed."""
        from ....domain.music.entities import Track as TrackType

        assert isinstance(track, TrackType)

        parts: list[str] = [
            f"**{index}.** [{truncate(track.title, UIConstants.TITLE_TRUNCATION)}]({track.webpage_url})"
        ]

        artist_or_uploader = track.artist or track.uploader
        if artist_or_uploader:
            parts.append(truncate(artist_or_uploader, 48))

        duration = format_duration(track.duration_seconds)
        if duration:
            parts.append(duration)

        if track.like_count is not None:
            parts.append(f"{track.like_count:,} likes")

        if track.requested_by_id:
            parts.append(f"req <@{track.requested_by_id}>")
        elif track.requested_by_name:
            parts.append(f"req {truncate(track.requested_by_name, 24)}")

        return " — ".join(parts)


setup = NowPlayingCog.setup
