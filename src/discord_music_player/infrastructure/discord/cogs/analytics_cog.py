"""Analytics slash commands for music statistics and charts."""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from discord_music_player.domain.shared.messages import DiscordUIMessages, LogTemplates
from discord_music_player.utils.reply import format_duration

if TYPE_CHECKING:
    from ....config.container import Container

logger = logging.getLogger(__name__)

BLURPLE = 0x5865F2
WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


class AnalyticsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.container: Container = bot.container  # type: ignore[attr-defined]

    @app_commands.command(name="stats", description="Show server music statistics")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        guild_id = interaction.guild_id
        history_repo = self.container.history_repository

        total = await history_repo.get_total_tracks(guild_id)
        if total == 0:
            await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
            return

        unique = await history_repo.get_unique_tracks(guild_id)
        listen_time = await history_repo.get_total_listen_time(guild_id)
        top_tracks = await history_repo.get_most_played(guild_id, limit=5)
        top_requesters = await history_repo.get_top_requesters(guild_id, limit=1)
        skip_rate = await history_repo.get_skip_rate(guild_id)

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_SERVER_STATS,
            color=BLURPLE,
        )
        embed.add_field(name="Total Plays", value=str(total), inline=True)
        embed.add_field(name="Unique Songs", value=str(unique), inline=True)
        embed.add_field(name="Listen Time", value=format_duration(listen_time), inline=True)

        if top_tracks:
            track, count = top_tracks[0]
            embed.add_field(name="Top Track", value=f"{track.title} ({count} plays)", inline=True)

        if top_requesters:
            _, name, count = top_requesters[0]
            embed.add_field(name="Most Active", value=f"{name} ({count} plays)", inline=True)

        embed.add_field(name="Skip Rate", value=f"{skip_rate:.0%}", inline=True)

        # Generate chart for top 5 tracks
        chart_file = None
        if top_tracks:
            try:
                chart_gen = self.container.chart_generator
                labels = [t.title[:40] for t, _ in top_tracks]
                values = [c for _, c in top_tracks]
                png = await chart_gen.async_horizontal_bar_chart(
                    labels, values, "Top 5 Most Played"
                )
                chart_file = chart_gen.to_discord_file(png, "top_tracks.png")
                embed.set_image(url="attachment://top_tracks.png")
                logger.debug(LogTemplates.ANALYTICS_CHART_GENERATED, "top_tracks", guild_id)
            except Exception:
                logger.exception("Failed to generate stats chart")

        await interaction.followup.send(embed=embed, file=chart_file)

    @app_commands.command(name="top", description="Show leaderboards")
    @app_commands.describe(category="What to rank")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Tracks", value="tracks"),
            app_commands.Choice(name="Users", value="users"),
            app_commands.Choice(name="Skipped", value="skipped"),
        ]
    )
    @app_commands.guild_only()
    async def top(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()

        guild_id = interaction.guild_id
        history_repo = self.container.history_repository
        cat = category.value if category else "tracks"

        if cat == "tracks":
            data = await history_repo.get_most_played(guild_id, limit=10)
            if not data:
                await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
                return

            labels = [t.title[:40] for t, _ in data]
            values = [c for _, c in data]
            title = DiscordUIMessages.EMBED_TOP_TRACKS
            lines = [f"**{i+1}.** {t.title[:50]} — {c} plays" for i, (t, c) in enumerate(data)]

        elif cat == "users":
            raw = await history_repo.get_top_requesters(guild_id, limit=10)
            if not raw:
                await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
                return

            labels = [name[:30] for _, name, _ in raw]
            values = [c for _, _, c in raw]
            title = DiscordUIMessages.EMBED_TOP_USERS
            lines = [f"**{i+1}.** {name} — {c} plays" for i, (_, name, c) in enumerate(raw)]

        else:  # skipped
            raw_skipped = await history_repo.get_most_skipped(guild_id, limit=10)
            if not raw_skipped:
                await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
                return

            labels = [t[:40] for t, _ in raw_skipped]
            values = [c for _, c in raw_skipped]
            title = DiscordUIMessages.EMBED_TOP_SKIPPED
            lines = [
                f"**{i+1}.** {t[:50]} — {c} skips" for i, (t, c) in enumerate(raw_skipped)
            ]

        embed = discord.Embed(title=title, description="\n".join(lines), color=BLURPLE)

        chart_file = None
        try:
            chart_gen = self.container.chart_generator
            png = await chart_gen.async_horizontal_bar_chart(labels, values, title)
            chart_file = chart_gen.to_discord_file(png, "leaderboard.png")
            embed.set_image(url="attachment://leaderboard.png")
            logger.debug(LogTemplates.ANALYTICS_CHART_GENERATED, "leaderboard", guild_id)
        except Exception:
            logger.exception("Failed to generate leaderboard chart")

        await interaction.followup.send(embed=embed, file=chart_file)

    @app_commands.command(name="mystats", description="Show your personal music stats")
    @app_commands.guild_only()
    async def mystats(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        guild_id = interaction.guild_id
        user_id = interaction.user.id
        history_repo = self.container.history_repository

        user_stats = await history_repo.get_user_stats(guild_id, user_id)
        if user_stats["total_tracks"] == 0:
            await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
            return

        top_tracks = await history_repo.get_user_top_tracks(guild_id, user_id, limit=5)

        embed = discord.Embed(
            title=DiscordUIMessages.EMBED_USER_STATS,
            color=BLURPLE,
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="Total Plays", value=str(user_stats["total_tracks"]), inline=True)
        embed.add_field(name="Unique Songs", value=str(user_stats["unique_tracks"]), inline=True)
        embed.add_field(
            name="Listen Time",
            value=format_duration(user_stats["total_listen_time"]),
            inline=True,
        )
        embed.add_field(name="Skip Rate", value=f"{user_stats['skip_rate']:.0%}", inline=True)

        if top_tracks:
            top_lines = [f"{i+1}. {t[:50]} ({c}x)" for i, (t, c) in enumerate(top_tracks)]
            embed.add_field(name="Your Top Songs", value="\n".join(top_lines), inline=False)

        # Genre pie chart (lazy classify)
        chart_file = None
        genre_data = await self._get_user_genre_data(guild_id, user_id)
        if genre_data:
            try:
                chart_gen = self.container.chart_generator
                genre_labels, genre_values = zip(*genre_data.items())
                png = await chart_gen.async_pie_chart(
                    list(genre_labels), list(genre_values), "Your Genre Mix"
                )
                chart_file = chart_gen.to_discord_file(png, "genres.png")
                embed.set_image(url="attachment://genres.png")
            except Exception:
                logger.exception("Failed to generate genre chart")

        await interaction.followup.send(embed=embed, file=chart_file)

    async def _get_user_genre_data(self, guild_id: int, user_id: int) -> dict[str, int] | None:
        """Get genre distribution for a user, classifying uncached tracks on demand."""
        history_repo = self.container.history_repository
        genre_repo = self.container.genre_repository
        classifier = self.container.genre_classifier

        # Get user's tracks with IDs
        rows = await history_repo._db.fetch_all(
            """
            SELECT track_id, title, artist
            FROM track_history
            WHERE guild_id = ? AND requested_by_id = ?
            """,
            (guild_id, user_id),
        )
        if not rows:
            return None

        track_ids = list({row["track_id"] for row in rows})

        # Look up cached genres
        cached = await genre_repo.get_genres(track_ids)
        uncached_ids = [tid for tid in track_ids if tid not in cached]

        # Classify uncached tracks
        if uncached_ids and classifier.is_available():
            id_to_desc = {}
            for row in rows:
                if row["track_id"] in uncached_ids and row["track_id"] not in id_to_desc:
                    desc = row["title"]
                    if row.get("artist"):
                        desc = f"{row['title']} - {row['artist']}"
                    id_to_desc[row["track_id"]] = desc

            tracks_to_classify = [(tid, id_to_desc.get(tid)) for tid in uncached_ids]
            new_genres = await classifier.classify_tracks(tracks_to_classify)
            if new_genres:
                await genre_repo.save_genres(new_genres)
                cached.update(new_genres)
        elif uncached_ids:
            # AI not available, mark as Unknown
            for tid in uncached_ids:
                cached[tid] = "Unknown"

        # Build per-track-id play count, then aggregate by genre
        track_id_counts: Counter[str] = Counter()
        for row in rows:
            track_id_counts[row["track_id"]] += 1

        genre_counts: Counter[str] = Counter()
        for tid, count in track_id_counts.items():
            genre = cached.get(tid, "Unknown")
            genre_counts[genre] += count

        # Filter out small slices and sort
        if not genre_counts:
            return None

        return dict(genre_counts.most_common(10))

    @app_commands.command(name="activity", description="Show listening activity over time")
    @app_commands.describe(period="Time period to analyze")
    @app_commands.choices(
        period=[
            app_commands.Choice(name="Daily (last 30 days)", value="daily"),
            app_commands.Choice(name="Weekly (by day of week)", value="weekly"),
            app_commands.Choice(name="Hourly (by hour of day)", value="hourly"),
        ]
    )
    @app_commands.guild_only()
    async def activity(
        self,
        interaction: discord.Interaction,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        await interaction.response.defer()

        guild_id = interaction.guild_id
        history_repo = self.container.history_repository
        chart_gen = self.container.chart_generator
        p = period.value if period else "daily"

        total = await history_repo.get_total_tracks(guild_id)
        if total == 0:
            await interaction.followup.send(DiscordUIMessages.ANALYTICS_NO_DATA)
            return

        embed = discord.Embed(title=DiscordUIMessages.EMBED_ACTIVITY, color=BLURPLE)
        chart_file = None

        try:
            if p == "daily":
                data = await history_repo.get_activity_by_day(guild_id, days=30)
                if data:
                    labels = [d for d, _ in data]
                    values = [c for _, c in data]
                    png = await chart_gen.async_line_chart(labels, values, "Daily Plays (Last 30 Days)")
                    chart_file = chart_gen.to_discord_file(png, "activity.png")
                    embed.set_image(url="attachment://activity.png")
                    embed.description = f"**{sum(values)}** total plays over **{len(data)}** active days"

            elif p == "weekly":
                data = await history_repo.get_activity_by_weekday(guild_id)
                if data:
                    # Fill all 7 days
                    day_map = dict(data)
                    labels = WEEKDAY_NAMES
                    values = [day_map.get(i, 0) for i in range(7)]
                    png = await chart_gen.async_bar_chart(labels, values, "Plays by Day of Week")
                    chart_file = chart_gen.to_discord_file(png, "activity.png")
                    embed.set_image(url="attachment://activity.png")
                    peak_day = WEEKDAY_NAMES[values.index(max(values))]
                    embed.description = f"Most active day: **{peak_day}**"

            else:  # hourly
                data = await history_repo.get_activity_by_hour(guild_id)
                if data:
                    hour_map = dict(data)
                    labels = [f"{h}:00" for h in range(24)]
                    values = [hour_map.get(h, 0) for h in range(24)]
                    png = await chart_gen.async_bar_chart(labels, values, "Plays by Hour of Day")
                    chart_file = chart_gen.to_discord_file(png, "activity.png")
                    embed.set_image(url="attachment://activity.png")
                    peak_hour = values.index(max(values))
                    embed.description = f"Peak hour: **{peak_hour}:00**"

            logger.debug(LogTemplates.ANALYTICS_CHART_GENERATED, p, guild_id)
        except Exception:
            logger.exception("Failed to generate activity chart")

        if not embed.description:
            embed.description = "Not enough data for this period."

        await interaction.followup.send(embed=embed, file=chart_file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AnalyticsCog(bot))
