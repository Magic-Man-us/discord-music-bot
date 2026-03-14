"""Analytics slash commands for music statistics and charts."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from discord_music_player.domain.shared.constants import AnalyticsConstants, UIConstants
from discord_music_player.domain.shared.enums import ActivityPeriod, LeaderboardCategory, LeaderboardTimeRange, Weekday
from discord_music_player.domain.shared.types import DiscordSnowflake, TrackForClassification, TrackGenreMap, UserIdField
from discord_music_player.infrastructure.discord.cogs.base_cog import BaseCog
from discord_music_player.utils.reply import format_duration

if TYPE_CHECKING:
    from ...charts.chart_generator import ChartGenerator
    from ...persistence.repositories.history_repository import GenreTrackInfo

_LEADERBOARD_CHART_FILENAME: str = "leaderboard.png"
_NO_MUSIC_YET = "No music has been played yet in this server."


class AnalyticsCog(BaseCog):

    async def _send_with_chart(
        self,
        interaction: discord.Interaction,
        embed: discord.Embed,
        chart_file: discord.File | None,
    ) -> None:
        """Send a followup with an optional chart attachment."""
        if chart_file is not None:
            await interaction.followup.send(embed=embed, file=chart_file)
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="stats", description="Show server music statistics")
    @app_commands.guild_only()
    async def stats(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        history_repo = self.container.history_repository

        total = await history_repo.get_total_tracks(guild_id)
        if total == 0:
            await interaction.followup.send(_NO_MUSIC_YET, ephemeral=True)
            return

        unique = await history_repo.get_unique_tracks(guild_id)
        listen_time = await history_repo.get_total_listen_time(guild_id)
        top_tracks = await history_repo.get_most_played(guild_id, limit=5)
        top_requesters = await history_repo.get_top_requesters(guild_id, limit=1)
        skip_rate = await history_repo.get_skip_rate(guild_id)

        embed = discord.Embed(
            title="Server Music Stats",
            color=AnalyticsConstants.BLURPLE,
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
                labels = [t.title[:AnalyticsConstants.CHART_LABEL_TRUNCATION] for t, _ in top_tracks]
                values = [c for _, c in top_tracks]
                png = await chart_gen.async_horizontal_bar_chart(
                    labels, values, "Top 5 Most Played"
                )
                chart_file = chart_gen.to_discord_file(png, "top_tracks.png")
                embed.set_image(url="attachment://top_tracks.png")
                self.logger.debug("Generated %s chart for guild %s", "top_tracks", guild_id)
            except Exception:
                self.logger.exception("Failed to generate stats chart")

        await self._send_with_chart(interaction, embed, chart_file)

    # -- Leaderboards --

    @app_commands.command(name="top", description="Show leaderboards")
    @app_commands.describe(category="What to rank", period="Time range")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="Tracks", value="tracks"),
            app_commands.Choice(name="Users", value="users"),
            app_commands.Choice(name="Skipped", value="skipped"),
        ],
        period=[
            app_commands.Choice(name="All Time", value="all"),
            app_commands.Choice(name="Last 7 Days", value="7d"),
            app_commands.Choice(name="Last 30 Days", value="30d"),
        ],
    )
    @app_commands.guild_only()
    async def top(
        self,
        interaction: discord.Interaction,
        category: app_commands.Choice[str] | None = None,
        period: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        cat = category.value if category else LeaderboardCategory.TRACKS
        time_range = LeaderboardTimeRange(period.value) if period else LeaderboardTimeRange.ALL_TIME

        result = await self._fetch_leaderboard(guild_id, cat, time_range)
        if result is None:
            await interaction.followup.send(_NO_MUSIC_YET, ephemeral=True)
            return

        title, labels, values, lines = result
        embed = discord.Embed(
            title=title, description="\n".join(lines), color=AnalyticsConstants.BLURPLE,
        )

        chart_file = None
        try:
            chart_gen = self.container.chart_generator
            png = await chart_gen.async_horizontal_bar_chart(labels, values, title)
            chart_file = chart_gen.to_discord_file(png, _LEADERBOARD_CHART_FILENAME)
            embed.set_image(url=f"attachment://{_LEADERBOARD_CHART_FILENAME}")
            self.logger.debug("Generated leaderboard chart for guild %s", guild_id)
        except Exception:
            self.logger.exception("Failed to generate leaderboard chart")

        await self._send_with_chart(interaction, embed, chart_file)

    async def _fetch_leaderboard(
        self,
        guild_id: DiscordSnowflake,
        category: str,
        time_range: LeaderboardTimeRange = LeaderboardTimeRange.ALL_TIME,
    ) -> tuple[str, list[str], list[int], list[str]] | None:
        """Fetch leaderboard data and format for display.

        Returns ``(title, chart_labels, chart_values, embed_lines)`` or None if empty.
        """
        history_repo = self.container.history_repository
        limit = AnalyticsConstants.DEFAULT_LEADERBOARD_LIMIT
        label_trunc = AnalyticsConstants.CHART_LABEL_TRUNCATION
        line_trunc = AnalyticsConstants.LEADERBOARD_LINE_TRUNCATION
        suffix = "" if time_range == LeaderboardTimeRange.ALL_TIME else f" ({time_range.value})"

        if category == LeaderboardCategory.TRACKS:
            data = await history_repo.get_most_played_since(guild_id, time_range, limit=limit)
            if not data:
                return None
            return (
                f"Top Tracks{suffix}",
                [t.title[:label_trunc] for t, _ in data],
                [c for _, c in data],
                [
                    f"**{i + 1}.** {t.title[:line_trunc]} — {c} plays"
                    for i, (t, c) in enumerate(data)
                ],
            )

        if category == LeaderboardCategory.USERS:
            raw = await history_repo.get_top_requesters_since(guild_id, time_range, limit=limit)
            if not raw:
                return None
            return (
                f"Top Listeners{suffix}",
                [name[:label_trunc] for _, name, _ in raw],
                [c for _, _, c in raw],
                [f"**{i + 1}.** {name} — {c} plays" for i, (_, name, c) in enumerate(raw)],
            )

        # skipped
        raw_skipped = await history_repo.get_most_skipped_since(guild_id, time_range, limit=limit)
        if not raw_skipped:
            return None
        return (
            f"Most Skipped{suffix}",
            [t[:label_trunc] for t, _ in raw_skipped],
            [c for _, c in raw_skipped],
            [f"**{i + 1}.** {t[:line_trunc]} — {c} skips" for i, (t, c) in enumerate(raw_skipped)],
        )

    # -- Personal stats --

    @app_commands.command(name="mystats", description="Show your personal music stats")
    @app_commands.guild_only()
    async def mystats(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        user_id = interaction.user.id
        history_repo = self.container.history_repository

        user_stats = await history_repo.get_user_stats(guild_id, user_id)
        if user_stats.total_tracks == 0:
            await interaction.followup.send(_NO_MUSIC_YET, ephemeral=True)
            return

        top_tracks = await history_repo.get_user_top_tracks(guild_id, user_id, limit=5)

        embed = discord.Embed(
            title="Your Music Stats",
            color=AnalyticsConstants.BLURPLE,
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="Total Plays", value=str(user_stats.total_tracks), inline=True)
        embed.add_field(name="Unique Songs", value=str(user_stats.unique_tracks), inline=True)
        embed.add_field(
            name="Listen Time",
            value=format_duration(user_stats.total_listen_time),
            inline=True,
        )
        embed.add_field(name="Skip Rate", value=f"{user_stats.skip_rate:.0%}", inline=True)

        if top_tracks:
            top_lines = [f"{i+1}. {t[:50]} ({c}x)" for i, (t, c) in enumerate(top_tracks)]
            embed.add_field(name="Your Top Songs", value="\n".join(top_lines), inline=False)

        # Genre pie chart (lazy classify)
        chart_file = None
        genre_data = await self._get_user_genre_data(guild_id, user_id)
        if genre_data:
            try:
                chart_gen = self.container.chart_generator
                genre_labels, genre_values = zip(*genre_data.items(), strict=False)
                png = await chart_gen.async_pie_chart(
                    list(genre_labels), list(genre_values), "Your Genre Mix"
                )
                chart_file = chart_gen.to_discord_file(png, "genres.png")
                embed.set_image(url="attachment://genres.png")
            except Exception:
                self.logger.exception("Failed to generate genre chart")

        await self._send_with_chart(interaction, embed, chart_file)

    # -- Genre classification --

    async def _get_user_genre_data(
        self, guild_id: DiscordSnowflake, user_id: UserIdField
    ) -> dict[str, int] | None:
        """Get genre distribution for a user, classifying uncached tracks on demand."""
        history_repo = self.container.history_repository
        genre_repo = self.container.genre_repository

        rows = await history_repo.get_user_tracks_for_genre(guild_id, user_id)
        if not rows:
            return None

        track_ids = list({row.track_id for row in rows})

        cached = await genre_repo.get_genres(track_ids)
        uncached_ids = [tid for tid in track_ids if tid not in cached]

        if uncached_ids:
            await self._classify_uncached(rows, uncached_ids, cached)

        return self._aggregate_genre_counts(rows, cached)

    async def _classify_uncached(
        self,
        rows: list[GenreTrackInfo],
        uncached_ids: list[str],
        cached: TrackGenreMap,
    ) -> None:
        """Classify uncached track IDs via AI, or mark as unknown if unavailable."""
        classifier = self.container.genre_classifier
        genre_repo = self.container.genre_repository

        if not classifier.is_available():
            for tid in uncached_ids:
                cached[tid] = UIConstants.UNKNOWN_FALLBACK
            return

        uncached_set = set(uncached_ids)
        id_to_desc: dict[str, str] = {}
        for row in rows:
            if row.track_id in uncached_set and row.track_id not in id_to_desc:
                desc = f"{row.title} - {row.artist}" if row.artist else row.title
                id_to_desc[row.track_id] = desc

        tracks_to_classify = [
            TrackForClassification(track_id=tid, description=id_to_desc.get(tid))
            for tid in uncached_ids
        ]
        new_genres = await classifier.classify_tracks(tracks_to_classify)
        if new_genres:
            await genre_repo.save_genres(new_genres)
            cached.update(new_genres)

    @staticmethod
    def _aggregate_genre_counts(
        rows: list[GenreTrackInfo], cached: TrackGenreMap,
    ) -> dict[str, int] | None:
        """Count plays per genre from history rows and genre cache."""
        track_id_counts: Counter[str] = Counter(row.track_id for row in rows)

        genre_counts: Counter[str] = Counter()
        for tid, count in track_id_counts.items():
            genre = cached.get(tid, UIConstants.UNKNOWN_FALLBACK)
            genre_counts[genre] += count

        if not genre_counts:
            return None

        return dict(genre_counts.most_common(AnalyticsConstants.GENRE_TOP_N))

    # -- Activity charts --

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
        assert interaction.guild is not None
        await interaction.response.defer(ephemeral=True)

        guild_id = interaction.guild.id
        history_repo = self.container.history_repository
        p = period.value if period else ActivityPeriod.DAILY

        total = await history_repo.get_total_tracks(guild_id)
        if total == 0:
            await interaction.followup.send(_NO_MUSIC_YET, ephemeral=True)
            return

        embed = discord.Embed(title="Listening Activity", color=AnalyticsConstants.BLURPLE)
        chart_file = None

        try:
            chart_file = await self._build_activity_chart(guild_id, p, embed)
            self.logger.debug("Generated %s chart for guild %s", p, guild_id)
        except Exception:
            self.logger.exception("Failed to generate activity chart")

        if not embed.description:
            embed.description = "Not enough data for this period."

        await self._send_with_chart(interaction, embed, chart_file)

    async def _build_activity_chart(
        self,
        guild_id: DiscordSnowflake,
        period: str,
        embed: discord.Embed,
    ) -> discord.File | None:
        """Fetch activity data, generate chart, and set embed description.

        Returns the chart File or None if there's no data for the period.
        """
        if period == ActivityPeriod.DAILY:
            return await self._build_daily_chart(guild_id, embed)

        if period == ActivityPeriod.WEEKLY:
            return await self._build_weekly_chart(guild_id, embed)

        return await self._build_hourly_chart(guild_id, embed)

    async def _build_daily_chart(
        self,
        guild_id: DiscordSnowflake,
        embed: discord.Embed,
    ) -> discord.File | None:
        data = await self.container.history_repository.get_activity_by_day(
            guild_id, days=AnalyticsConstants.ACTIVITY_DAYS_WINDOW,
        )
        if not data:
            return None

        labels = [d for d, _ in data]
        values = [c for _, c in data]
        chart_gen = self.container.chart_generator
        png = await chart_gen.async_line_chart(labels, values, "Daily Plays (Last 30 Days)")
        embed.description = f"**{sum(values)}** total plays over **{len(data)}** active days"
        return self._attach_chart(embed, chart_gen, png)

    async def _build_weekly_chart(
        self,
        guild_id: DiscordSnowflake,
        embed: discord.Embed,
    ) -> discord.File | None:
        data = await self.container.history_repository.get_activity_by_weekday(guild_id)
        if not data:
            return None

        day_map = dict(data)
        weekdays = list(Weekday)
        labels = [str(d) for d in weekdays]
        values = [day_map.get(i, 0) for i in range(len(weekdays))]
        chart_gen = self.container.chart_generator
        png = await chart_gen.async_bar_chart(labels, values, "Plays by Day of Week")
        peak_day = weekdays[values.index(max(values))]
        embed.description = f"Most active day: **{peak_day}**"
        return self._attach_chart(embed, chart_gen, png)

    async def _build_hourly_chart(
        self,
        guild_id: DiscordSnowflake,
        embed: discord.Embed,
    ) -> discord.File | None:
        data = await self.container.history_repository.get_activity_by_hour(guild_id)
        if not data:
            return None

        hour_map = dict(data)
        labels = [f"{h}:00" for h in range(24)]
        values = [hour_map.get(h, 0) for h in range(24)]
        chart_gen = self.container.chart_generator
        png = await chart_gen.async_bar_chart(labels, values, "Plays by Hour of Day")
        peak_hour = values.index(max(values))
        embed.description = f"Peak hour: **{peak_hour}:00**"
        return self._attach_chart(embed, chart_gen, png)

    @staticmethod
    def _attach_chart(embed: discord.Embed, chart_gen: ChartGenerator, png: bytes) -> discord.File:
        filename = AnalyticsConstants.ACTIVITY_CHART_FILENAME
        chart_file = chart_gen.to_discord_file(png, filename)
        embed.set_image(url=f"attachment://{filename}")
        return chart_file


setup = AnalyticsCog.setup
