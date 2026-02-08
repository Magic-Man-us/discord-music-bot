"""Tests for analytics: repository queries, chart generator, genre classifier, genre repository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.value_objects import TrackId


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
        from pydantic import SecretStr
        from discord_music_player.config.settings import AISettings
        return AISettings(api_key=SecretStr("test-key"), model="gpt-5-mini")

    @pytest.fixture
    def classifier(self, ai_settings):
        from discord_music_player.infrastructure.ai.genre_classifier import OpenAIGenreClassifier
        return OpenAIGenreClassifier(ai_settings)

    def test_is_available(self, classifier):
        assert classifier.is_available() is True

    def test_is_not_available_no_key(self):
        from pydantic import SecretStr
        from discord_music_player.config.settings import AISettings
        from discord_music_player.infrastructure.ai.genre_classifier import OpenAIGenreClassifier
        settings = AISettings(api_key=SecretStr(""), model="gpt-5-mini")
        c = OpenAIGenreClassifier(settings)
        assert c.is_available() is False

    async def test_classify_empty_list(self, classifier):
        result = await classifier.classify_tracks([])
        assert result == {}

    async def test_classify_tracks_success(self, classifier):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"genres": {"t1": "Rock", "t2": "Pop"}}'

        mock_options = MagicMock()
        mock_options.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.with_options.return_value = mock_options
        classifier._client = mock_client

        result = await classifier.classify_tracks([("t1", "Rock Anthem - Band A"), ("t2", "Pop Hit - Singer B")])
        assert result["t1"] == "Rock"
        assert result["t2"] == "Pop"

    async def test_classify_tracks_api_failure(self, classifier):
        mock_options = MagicMock()
        mock_options.chat.completions.create = AsyncMock(side_effect=Exception("API error"))
        mock_client = MagicMock()
        mock_client.with_options.return_value = mock_options
        classifier._client = mock_client

        result = await classifier.classify_tracks([("t1", "Some Song")])
        assert result == {"t1": "Unknown"}

    async def test_classify_tracks_invalid_genre_mapped_to_other(self, classifier):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"genres": {"t1": "NotAGenre"}}'

        mock_options = MagicMock()
        mock_options.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_client = MagicMock()
        mock_client.with_options.return_value = mock_options
        classifier._client = mock_client

        result = await classifier.classify_tracks([("t1", "Unknown Song")])
        assert result["t1"] == "Other"
