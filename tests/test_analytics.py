"""Tests for analytics: repository queries, chart generator, genre classifier, genre repository, and cog commands."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio
from discord.ext import commands

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.messages import DiscordUIMessages
from discord_music_player.infrastructure.discord.cogs.analytics_cog import AnalyticsCog


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def make_track():
    """Factory for creating test tracks."""
    def _make(track_id="t1", title="Song A", artist="Artist A", duration=180, requester_id=100, requester_name="Alice"):
        return Track(
            id=TrackId(track_id),
            title=title,
            webpage_url=f"https://youtube.com/watch?v={track_id}",
            duration_seconds=duration,
            artist=artist,
            requested_by_id=requester_id,
            requested_by_name=requester_name,
        )
    return _make


@pytest_asyncio.fixture
async def genre_repository(in_memory_database):
    from discord_music_player.infrastructure.persistence.repositories.genre_repository import (
        SQLiteGenreCacheRepository,
    )
    return SQLiteGenreCacheRepository(in_memory_database)


# ============================================================================
# History Repository Analytics Tests
# ============================================================================


class TestHistoryAnalytics:
    """Tests for the 11 new analytics methods on the history repository."""

    async def _seed(self, repo, make_track, guild_id=1):
        """Seed data: 3 tracks by 2 users, some skipped."""
        t1 = make_track("t1", "Rock Anthem", "Band A", 200, 100, "Alice")
        t2 = make_track("t2", "Pop Hit", "Singer B", 180, 200, "Bob")
        t3 = make_track("t3", "Chill Vibes", "DJ C", 240, 100, "Alice")

        # t1 played 3 times
        for _ in range(3):
            await repo.record_play(guild_id, t1)
        # t2 played 2 times, 1 skipped
        for _ in range(2):
            await repo.record_play(guild_id, t2)
        await repo.mark_finished(guild_id, t2.id, skipped=True)
        # t3 played 1 time, skipped
        await repo.record_play(guild_id, t3)
        await repo.mark_finished(guild_id, t3.id, skipped=True)

    async def test_get_total_tracks(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        assert await history_repository.get_total_tracks(1) == 6

    async def test_get_total_tracks_empty(self, history_repository):
        assert await history_repository.get_total_tracks(999) == 0

    async def test_get_unique_tracks(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        assert await history_repository.get_unique_tracks(1) == 3

    async def test_get_total_listen_time(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        # 3*200 + 2*180 + 1*240 = 600 + 360 + 240 = 1200
        assert await history_repository.get_total_listen_time(1) == 1200

    async def test_get_top_requesters(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        top = await history_repository.get_top_requesters(1, limit=10)
        assert len(top) == 2
        # Alice requested 4 (3+1), Bob requested 2
        assert top[0] == (100, "Alice", 4)
        assert top[1] == (200, "Bob", 2)

    async def test_get_skip_rate(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        rate = await history_repository.get_skip_rate(1)
        # 2 skipped out of 6 = 0.333...
        assert abs(rate - 2 / 6) < 0.01

    async def test_get_skip_rate_empty(self, history_repository):
        rate = await history_repository.get_skip_rate(999)
        assert rate == 0.0

    async def test_get_most_skipped(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        skipped = await history_repository.get_most_skipped(1, limit=10)
        assert len(skipped) >= 1
        # Both t2 and t3 were skipped once each
        titles = {t for t, _ in skipped}
        assert "Pop Hit" in titles or "Chill Vibes" in titles

    async def test_get_user_stats(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        stats = await history_repository.get_user_stats(1, 100)  # Alice
        assert stats["total_tracks"] == 4  # 3 + 1
        assert stats["unique_tracks"] == 2  # t1, t3
        assert stats["total_listen_time"] == 3 * 200 + 240  # 840

    async def test_get_user_stats_empty(self, history_repository):
        stats = await history_repository.get_user_stats(999, 999)
        assert stats["total_tracks"] == 0

    async def test_get_user_top_tracks(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        top = await history_repository.get_user_top_tracks(1, 100, limit=5)  # Alice
        assert len(top) == 2
        assert top[0] == ("Rock Anthem", 3)
        assert top[1] == ("Chill Vibes", 1)

    async def test_get_activity_by_day(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        data = await history_repository.get_activity_by_day(1, days=30)
        assert len(data) >= 1
        # All plays happened today, so should be 1 day with count 6
        total = sum(c for _, c in data)
        assert total == 6

    async def test_get_activity_by_hour(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        data = await history_repository.get_activity_by_hour(1)
        assert len(data) >= 1
        total = sum(c for _, c in data)
        assert total == 6

    async def test_get_activity_by_weekday(self, history_repository, make_track):
        await self._seed(history_repository, make_track)
        data = await history_repository.get_activity_by_weekday(1)
        assert len(data) >= 1
        total = sum(c for _, c in data)
        assert total == 6


# ============================================================================
# Genre Repository Tests
# ============================================================================


class TestGenreRepository:

    async def test_save_and_get_genres(self, genre_repository):
        await genre_repository.save_genres({"t1": "Rock", "t2": "Pop"})
        result = await genre_repository.get_genres(["t1", "t2", "t3"])
        assert result == {"t1": "Rock", "t2": "Pop"}

    async def test_get_genres_empty(self, genre_repository):
        result = await genre_repository.get_genres([])
        assert result == {}

    async def test_save_genres_empty(self, genre_repository):
        await genre_repository.save_genres({})  # should not raise

    async def test_upsert_overwrites(self, genre_repository):
        await genre_repository.save_genres({"t1": "Rock"})
        await genre_repository.save_genres({"t1": "Metal"})
        result = await genre_repository.get_genres(["t1"])
        assert result == {"t1": "Metal"}


# ============================================================================
# Chart Generator Tests
# ============================================================================


class TestChartGenerator:

    @pytest.fixture
    def chart_gen(self):
        from discord_music_player.infrastructure.charts.chart_generator import ChartGenerator
        return ChartGenerator()

    def test_horizontal_bar_chart_returns_png(self, chart_gen):
        result = chart_gen.horizontal_bar_chart(["A", "B", "C"], [10, 5, 3], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_line_chart_returns_png(self, chart_gen):
        result = chart_gen.line_chart(["Mon", "Tue", "Wed"], [1, 3, 2], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_bar_chart_returns_png(self, chart_gen):
        result = chart_gen.bar_chart(["A", "B"], [5, 8], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_pie_chart_returns_png(self, chart_gen):
        result = chart_gen.pie_chart(["Rock", "Pop", "Jazz"], [50, 30, 20], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    def test_to_discord_file(self, chart_gen):
        import discord
        png = chart_gen.horizontal_bar_chart(["A"], [1], "Test")
        f = chart_gen.to_discord_file(png, "test.png")
        assert isinstance(f, discord.File)

    async def test_async_horizontal_bar_chart(self, chart_gen):
        result = await chart_gen.async_horizontal_bar_chart(["A"], [1], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_async_pie_chart(self, chart_gen):
        result = await chart_gen.async_pie_chart(["X", "Y"], [60, 40], "Test")
        assert isinstance(result, bytes)
        assert result[:8] == b"\x89PNG\r\n\x1a\n"


# ============================================================================
# Genre Classifier Tests
# ============================================================================


class TestGenreClassifier:

    @pytest.fixture
    def ai_settings(self):
        from discord_music_player.config.settings import AISettings
        return AISettings(model="openai:gpt-5-mini")

    @pytest.fixture
    def classifier(self, ai_settings):
        from discord_music_player.infrastructure.ai.genre_classifier import AIGenreClassifier
        return AIGenreClassifier(ai_settings)

    def test_is_available(self, classifier):
        with patch(
            "discord_music_player.infrastructure.ai.genre_classifier.Agent"
        ):
            assert classifier.is_available() is True

    def test_is_not_available_on_error(self):
        from discord_music_player.config.settings import AISettings
        from discord_music_player.infrastructure.ai.genre_classifier import AIGenreClassifier
        settings = AISettings(model="openai:gpt-5-mini")
        c = AIGenreClassifier(settings)
        with patch(
            "discord_music_player.infrastructure.ai.genre_classifier.Agent",
            side_effect=Exception("fail"),
        ):
            assert c.is_available() is False

    async def test_classify_empty_list(self, classifier):
        result = await classifier.classify_tracks([])
        assert result == {}

    async def test_classify_tracks_success(self, classifier):
        from discord_music_player.infrastructure.ai.genre_classifier import GenreClassificationResponse

        mock_output = GenreClassificationResponse(genres={"t1": "Rock", "t2": "Pop"})
        mock_result = MagicMock()
        mock_result.output = mock_output

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        classifier._agent = mock_agent

        result = await classifier.classify_tracks([("t1", "Rock Anthem - Band A"), ("t2", "Pop Hit - Singer B")])
        assert result["t1"] == "Rock"
        assert result["t2"] == "Pop"

    async def test_classify_tracks_api_failure(self, classifier):
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("API error"))
        classifier._agent = mock_agent

        result = await classifier.classify_tracks([("t1", "Some Song")])
        assert result == {"t1": "Unknown"}

    async def test_classify_tracks_invalid_genre_mapped_to_other(self, classifier):
        from discord_music_player.infrastructure.ai.genre_classifier import GenreClassificationResponse

        mock_output = GenreClassificationResponse(genres={"t1": "NotAGenre"})
        mock_result = MagicMock()
        mock_result.output = mock_output

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        classifier._agent = mock_agent

        result = await classifier.classify_tracks([("t1", "Unknown Song")])
        assert result["t1"] == "Other"

    async def test_get_agent_creates_agent(self, classifier):
        """Should create an Agent on first call."""
        with patch(
            "discord_music_player.infrastructure.ai.genre_classifier.Agent"
        ) as mock_agent_cls:
            agent = classifier._get_agent()
            mock_agent_cls.assert_called_once()
            assert classifier._agent is not None

    async def test_classify_batch_empty_response(self, classifier):
        """Should return Other for all tracks when AI returns empty genres."""
        from discord_music_player.infrastructure.ai.genre_classifier import GenreClassificationResponse

        mock_output = GenreClassificationResponse(genres={})
        mock_result = MagicMock()
        mock_result.output = mock_output

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        classifier._agent = mock_agent

        result = await classifier.classify_tracks([("t1", "Song A"), ("t2", "Song B")])
        # "Unknown" is not in GENRE_VOCABULARY, so it maps to "Other"
        assert result == {"t1": "Other", "t2": "Other"}

    async def test_classify_tracks_batching(self, classifier):
        """Should process tracks in batches of BATCH_SIZE."""
        from discord_music_player.infrastructure.ai.genre_classifier import BATCH_SIZE, GenreClassificationResponse

        call_count = 0

        async def mock_run(prompt, **kwargs):
            nonlocal call_count
            call_count += 1
            # Parse track IDs from the prompt
            genres = {}
            for line in prompt.split("\n"):
                if "id:" in line:
                    tid = line.split("id:")[1].split(" |")[0]
                    genres[tid] = "Rock"
            mock_result = MagicMock()
            mock_result.output = GenreClassificationResponse(genres=genres)
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=mock_run)
        classifier._agent = mock_agent

        # Create more tracks than one batch
        tracks = [(f"t{i}", f"Song {i}") for i in range(BATCH_SIZE + 5)]
        result = await classifier.classify_tracks(tracks)

        assert call_count == 2  # Two batches
        assert len(result) == BATCH_SIZE + 5

    async def test_classify_batch_none_description(self, classifier):
        """Should handle None descriptions gracefully."""
        from discord_music_player.infrastructure.ai.genre_classifier import GenreClassificationResponse

        mock_output = GenreClassificationResponse(genres={"t1": "Rock"})
        mock_result = MagicMock()
        mock_result.output = mock_output

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_result)
        classifier._agent = mock_agent

        result = await classifier.classify_tracks([("t1", None)])
        assert result["t1"] == "Rock"


# ============================================================================
# Analytics Cog Tests
# ============================================================================


@pytest.fixture
def mock_interaction():
    """Create a mock Discord Interaction for slash commands."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    interaction.guild = MagicMock()
    interaction.guild.id = 111111111
    interaction.guild_id = 111111111

    member = MagicMock(spec=discord.Member)
    member.id = 333333333
    member.display_name = "TestUser"
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://cdn.example.com/avatar.png"
    interaction.user = member

    return interaction


@pytest.fixture
def mock_history_repo():
    repo = MagicMock()
    repo.get_total_tracks = AsyncMock(return_value=50)
    repo.get_unique_tracks = AsyncMock(return_value=25)
    repo.get_total_listen_time = AsyncMock(return_value=9000)
    repo.get_skip_rate = AsyncMock(return_value=0.15)

    sample_track = Track(
        id=TrackId("t1"),
        title="Rock Anthem",
        webpage_url="https://youtube.com/watch?v=t1",
        duration_seconds=200,
        artist="Band A",
    )
    repo.get_most_played = AsyncMock(return_value=[(sample_track, 10)])
    repo.get_top_requesters = AsyncMock(return_value=[(100, "Alice", 30)])
    repo.get_most_skipped = AsyncMock(return_value=[("Pop Hit", 5)])
    repo.get_user_stats = AsyncMock(
        return_value={
            "total_tracks": 20,
            "unique_tracks": 10,
            "total_listen_time": 4000,
            "skip_rate": 0.1,
        }
    )
    repo.get_user_top_tracks = AsyncMock(return_value=[("Rock Anthem", 8), ("Chill Vibes", 4)])
    repo.get_activity_by_day = AsyncMock(return_value=[("2026-02-01", 10), ("2026-02-02", 15)])
    repo.get_activity_by_weekday = AsyncMock(return_value=[(0, 5), (1, 12), (3, 8)])
    repo.get_activity_by_hour = AsyncMock(return_value=[(14, 20), (15, 15), (20, 10)])
    repo.get_user_tracks_for_genre = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_chart_gen():
    gen = MagicMock()
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    gen.async_horizontal_bar_chart = AsyncMock(return_value=png_bytes)
    gen.async_bar_chart = AsyncMock(return_value=png_bytes)
    gen.async_line_chart = AsyncMock(return_value=png_bytes)
    gen.async_pie_chart = AsyncMock(return_value=png_bytes)
    gen.to_discord_file = MagicMock(return_value=MagicMock(spec=discord.File))
    return gen


@pytest.fixture
def mock_analytics_container(mock_history_repo, mock_chart_gen):
    container = MagicMock()
    container.history_repository = mock_history_repo
    container.chart_generator = mock_chart_gen
    container.genre_repository = MagicMock()
    container.genre_repository.get_genres = AsyncMock(return_value={})
    container.genre_classifier = MagicMock()
    container.genre_classifier.is_available = MagicMock(return_value=False)
    return container


@pytest.fixture
def analytics_cog(mock_analytics_container):
    bot = MagicMock(spec=commands.Bot)
    bot.container = mock_analytics_container
    return AnalyticsCog(bot)


class TestStatsCogCommand:
    """Tests for /stats slash command."""

    @pytest.mark.asyncio
    async def test_stats_success(self, analytics_cog, mock_interaction):
        """Should build embed with server stats and chart."""
        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        mock_interaction.response.defer.assert_called_once()
        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_SERVER_STATS in embed.title

        field_names = [f.name for f in embed.fields]
        assert "Total Plays" in field_names
        assert "Unique Songs" in field_names
        assert "Listen Time" in field_names
        assert "Skip Rate" in field_names

    @pytest.mark.asyncio
    async def test_stats_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when guild has no plays."""
        mock_history_repo.get_total_tracks = AsyncMock(return_value=0)

        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_stats_chart_failure_still_sends_embed(
        self, analytics_cog, mock_interaction, mock_chart_gen
    ):
        """Should still send embed even if chart generation fails."""
        mock_chart_gen.async_horizontal_bar_chart = AsyncMock(side_effect=Exception("chart error"))

        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        assert "embed" in call_kwargs

    @pytest.mark.asyncio
    async def test_stats_shows_top_track(self, analytics_cog, mock_interaction):
        """Should include top track field."""
        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_values = {f.name: f.value for f in embed.fields}
        assert "Top Track" in field_values
        assert "Rock Anthem" in field_values["Top Track"]

    @pytest.mark.asyncio
    async def test_stats_shows_most_active(self, analytics_cog, mock_interaction):
        """Should include most active user field."""
        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_values = {f.name: f.value for f in embed.fields}
        assert "Most Active" in field_values
        assert "Alice" in field_values["Most Active"]

    @pytest.mark.asyncio
    async def test_stats_no_top_tracks(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should omit top track field when no top tracks."""
        mock_history_repo.get_most_played = AsyncMock(return_value=[])

        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Top Track" not in field_names

    @pytest.mark.asyncio
    async def test_stats_no_requesters(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should omit most active field when no requesters."""
        mock_history_repo.get_top_requesters = AsyncMock(return_value=[])

        await analytics_cog.stats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Most Active" not in field_names


class TestTopCogCommand:
    """Tests for /top slash command."""

    @pytest.mark.asyncio
    async def test_top_tracks_default(self, analytics_cog, mock_interaction):
        """Should default to tracks category."""
        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=None)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_TOP_TRACKS in embed.title
        assert "Rock Anthem" in embed.description

    @pytest.mark.asyncio
    async def test_top_tracks_explicit(self, analytics_cog, mock_interaction):
        """Should show tracks leaderboard."""
        choice = MagicMock()
        choice.value = "tracks"

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_TOP_TRACKS in embed.title

    @pytest.mark.asyncio
    async def test_top_users(self, analytics_cog, mock_interaction):
        """Should show users leaderboard."""
        choice = MagicMock()
        choice.value = "users"

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_TOP_USERS in embed.title
        assert "Alice" in embed.description

    @pytest.mark.asyncio
    async def test_top_skipped(self, analytics_cog, mock_interaction):
        """Should show most skipped leaderboard."""
        choice = MagicMock()
        choice.value = "skipped"

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_TOP_SKIPPED in embed.title
        assert "Pop Hit" in embed.description

    @pytest.mark.asyncio
    async def test_top_tracks_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when no tracks."""
        mock_history_repo.get_most_played = AsyncMock(return_value=[])

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=None)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_top_users_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when no requesters."""
        mock_history_repo.get_top_requesters = AsyncMock(return_value=[])
        choice = MagicMock()
        choice.value = "users"

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=choice)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_top_skipped_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when no skipped tracks."""
        mock_history_repo.get_most_skipped = AsyncMock(return_value=[])
        choice = MagicMock()
        choice.value = "skipped"

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=choice)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_top_chart_failure_still_sends_embed(
        self, analytics_cog, mock_interaction, mock_chart_gen
    ):
        """Should still send embed even if chart generation fails."""
        mock_chart_gen.async_horizontal_bar_chart = AsyncMock(side_effect=Exception("chart error"))

        await analytics_cog.top.callback(analytics_cog, mock_interaction, category=None)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        assert "embed" in call_kwargs


class TestMystatsCogCommand:
    """Tests for /mystats slash command."""

    @pytest.mark.asyncio
    async def test_mystats_success(self, analytics_cog, mock_interaction):
        """Should build embed with user stats."""
        await analytics_cog.mystats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_USER_STATS in embed.title

        field_names = [f.name for f in embed.fields]
        assert "Total Plays" in field_names
        assert "Unique Songs" in field_names
        assert "Listen Time" in field_names
        assert "Skip Rate" in field_names

    @pytest.mark.asyncio
    async def test_mystats_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when user has no plays."""
        mock_history_repo.get_user_stats = AsyncMock(
            return_value={
                "total_tracks": 0,
                "unique_tracks": 0,
                "total_listen_time": 0,
                "skip_rate": 0.0,
            }
        )

        await analytics_cog.mystats.callback(analytics_cog, mock_interaction)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_mystats_includes_top_songs(self, analytics_cog, mock_interaction):
        """Should include user's top songs field."""
        await analytics_cog.mystats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_values = {f.name: f.value for f in embed.fields}
        assert "Your Top Songs" in field_values
        assert "Rock Anthem" in field_values["Your Top Songs"]

    @pytest.mark.asyncio
    async def test_mystats_no_top_tracks(
        self, analytics_cog, mock_interaction, mock_history_repo
    ):
        """Should omit top songs field when empty."""
        mock_history_repo.get_user_top_tracks = AsyncMock(return_value=[])

        await analytics_cog.mystats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        field_names = [f.name for f in embed.fields]
        assert "Your Top Songs" not in field_names

    @pytest.mark.asyncio
    async def test_mystats_genre_chart_failure_still_sends(
        self, analytics_cog, mock_interaction, mock_chart_gen, mock_history_repo
    ):
        """Should send embed even if genre chart fails."""
        # Set up some genre data so the chart path is triggered
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(
            return_value=[{"track_id": "t1", "title": "Song", "artist": "A"}]
        )
        analytics_cog.container.genre_repository.get_genres = AsyncMock(
            return_value={"t1": "Rock"}
        )
        mock_chart_gen.async_pie_chart = AsyncMock(side_effect=Exception("chart error"))

        await analytics_cog.mystats.callback(analytics_cog, mock_interaction)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        assert "embed" in call_kwargs


class TestActivityCogCommand:
    """Tests for /activity slash command."""

    @pytest.mark.asyncio
    async def test_activity_daily_default(self, analytics_cog, mock_interaction):
        """Should default to daily period."""
        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=None)

        mock_interaction.response.defer.assert_called_once()
        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert DiscordUIMessages.EMBED_ACTIVITY in embed.title
        assert "total plays" in embed.description

    @pytest.mark.asyncio
    async def test_activity_daily_explicit(self, analytics_cog, mock_interaction):
        """Should show daily chart."""
        choice = MagicMock()
        choice.value = "daily"

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "total plays" in embed.description

    @pytest.mark.asyncio
    async def test_activity_weekly(self, analytics_cog, mock_interaction):
        """Should show weekly chart with peak day."""
        choice = MagicMock()
        choice.value = "weekly"

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "Most active day" in embed.description

    @pytest.mark.asyncio
    async def test_activity_hourly(self, analytics_cog, mock_interaction):
        """Should show hourly chart with peak hour."""
        choice = MagicMock()
        choice.value = "hourly"

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=choice)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert "Peak hour" in embed.description

    @pytest.mark.asyncio
    async def test_activity_no_data(self, analytics_cog, mock_interaction, mock_history_repo):
        """Should send no-data message when guild has no plays."""
        mock_history_repo.get_total_tracks = AsyncMock(return_value=0)

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=None)

        args = mock_interaction.followup.send.call_args[0]
        assert args[0] == DiscordUIMessages.ANALYTICS_NO_DATA

    @pytest.mark.asyncio
    async def test_activity_chart_failure_shows_fallback(
        self, analytics_cog, mock_interaction, mock_chart_gen
    ):
        """Should show 'not enough data' fallback when chart fails."""
        mock_chart_gen.async_line_chart = AsyncMock(side_effect=Exception("chart error"))

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=None)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        # Chart failed, so description falls through to followup.send
        assert embed is not None

    @pytest.mark.asyncio
    async def test_activity_daily_empty_data(
        self, analytics_cog, mock_interaction, mock_history_repo
    ):
        """Should show fallback message when daily data is empty."""
        mock_history_repo.get_activity_by_day = AsyncMock(return_value=[])

        await analytics_cog.activity.callback(analytics_cog, mock_interaction, period=None)

        call_kwargs = mock_interaction.followup.send.call_args.kwargs
        embed = call_kwargs["embed"]
        assert embed.description == "Not enough data for this period."


class TestGetUserGenreData:
    """Tests for _get_user_genre_data helper method."""

    @pytest.mark.asyncio
    async def test_no_rows_returns_none(self, analytics_cog, mock_history_repo):
        """Should return None when user has no history."""
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(return_value=[])

        result = await analytics_cog._get_user_genre_data(111, 333)
        assert result is None

    @pytest.mark.asyncio
    async def test_cached_genres_used(self, analytics_cog, mock_history_repo):
        """Should use cached genres without calling classifier."""
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(
            return_value=[
                {"track_id": "t1", "title": "Rock Song", "artist": "A"},
                {"track_id": "t2", "title": "Pop Song", "artist": "B"},
            ]
        )
        analytics_cog.container.genre_repository.get_genres = AsyncMock(
            return_value={"t1": "Rock", "t2": "Pop"}
        )

        result = await analytics_cog._get_user_genre_data(111, 333)

        assert result == {"Rock": 1, "Pop": 1}
        analytics_cog.container.genre_classifier.classify_tracks.assert_not_called()

    @pytest.mark.asyncio
    async def test_uncached_marked_unknown_when_ai_unavailable(
        self, analytics_cog, mock_history_repo
    ):
        """Should mark uncached tracks as Unknown when AI is unavailable."""
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(
            return_value=[{"track_id": "t1", "title": "Song", "artist": "A"}]
        )
        analytics_cog.container.genre_repository.get_genres = AsyncMock(return_value={})
        analytics_cog.container.genre_classifier.is_available = MagicMock(return_value=False)

        result = await analytics_cog._get_user_genre_data(111, 333)

        assert result == {"Unknown": 1}

    @pytest.mark.asyncio
    async def test_uncached_classified_when_ai_available(
        self, analytics_cog, mock_history_repo
    ):
        """Should classify uncached tracks when AI is available."""
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(
            return_value=[{"track_id": "t1", "title": "Rock Song", "artist": "Band A"}]
        )
        analytics_cog.container.genre_repository.get_genres = AsyncMock(return_value={})
        analytics_cog.container.genre_classifier.is_available = MagicMock(return_value=True)
        analytics_cog.container.genre_classifier.classify_tracks = AsyncMock(
            return_value={"t1": "Rock"}
        )
        analytics_cog.container.genre_repository.save_genres = AsyncMock()

        result = await analytics_cog._get_user_genre_data(111, 333)

        assert result == {"Rock": 1}
        analytics_cog.container.genre_repository.save_genres.assert_called_once()

    @pytest.mark.asyncio
    async def test_genre_aggregation_by_play_count(self, analytics_cog, mock_history_repo):
        """Should aggregate genres by number of plays, not unique tracks."""
        mock_history_repo.get_user_tracks_for_genre = AsyncMock(
            return_value=[
                {"track_id": "t1", "title": "Song1", "artist": "A"},
                {"track_id": "t1", "title": "Song1", "artist": "A"},
                {"track_id": "t1", "title": "Song1", "artist": "A"},
                {"track_id": "t2", "title": "Song2", "artist": "B"},
            ]
        )
        analytics_cog.container.genre_repository.get_genres = AsyncMock(
            return_value={"t1": "Rock", "t2": "Pop"}
        )

        result = await analytics_cog._get_user_genre_data(111, 333)

        assert result["Rock"] == 3
        assert result["Pop"] == 1


class TestAnalyticsCogSetup:
    """Tests for cog setup function."""

    @pytest.mark.asyncio
    async def test_setup_adds_cog(self):
        """Should add AnalyticsCog to bot."""
        from discord_music_player.infrastructure.discord.cogs.analytics_cog import setup

        bot = MagicMock(spec=commands.Bot)
        bot.container = MagicMock()
        bot.add_cog = AsyncMock()

        await setup(bot)

        bot.add_cog.assert_called_once()
        cog = bot.add_cog.call_args[0][0]
        assert isinstance(cog, AnalyticsCog)
