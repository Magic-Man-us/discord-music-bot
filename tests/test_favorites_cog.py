"""Unit tests for FavoritesCog slash commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.infrastructure.discord.cogs.favorites_cog import FavoritesCog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_track(track_id: str = "abc123", title: str = "Test Song") -> Track:
    return Track(
        id=TrackId(value=track_id),
        title=title,
        webpage_url=f"https://youtube.com/watch?v={track_id}",
        stream_url="https://stream.example.com/audio.mp3",
        duration_seconds=200,
        artist="Test Artist",
    )


def _make_interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock(return_value=MagicMock(id=123456))
    interaction.guild = MagicMock()
    interaction.guild.id = 111
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = 222
    interaction.user.display_name = "TestUser"
    interaction.user.bot = False
    interaction.user.voice = MagicMock()
    interaction.user.voice.channel = MagicMock()
    return interaction


def _make_container() -> MagicMock:
    container = MagicMock()
    container.session_repository = MagicMock()
    container.session_repository.get = AsyncMock(return_value=None)
    container.favorites_repository = MagicMock()
    container.favorites_repository.add = AsyncMock(return_value=True)
    container.favorites_repository.get_all = AsyncMock(return_value=[])
    container.favorites_repository.remove = AsyncMock(return_value=True)
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0
    container.voice_adapter = MagicMock()
    container.voice_adapter.connect = AsyncMock()
    container.voice_adapter.is_connected = MagicMock(return_value=True)
    container.queue_service = MagicMock()
    container.queue_service.enqueue_batch = AsyncMock()
    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()
    return container


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def container() -> MagicMock:
    return _make_container()


@pytest.fixture
def cog(container: MagicMock) -> FavoritesCog:
    bot = MagicMock()
    return FavoritesCog(bot=bot, container=container)


@pytest.fixture
def interaction() -> MagicMock:
    return _make_interaction()


# ---------------------------------------------------------------------------
# favorites_add
# ---------------------------------------------------------------------------

GUARD_PATH = "discord_music_player.infrastructure.discord.cogs.favorites_cog.ensure_user_in_voice_and_warm"
VOICE_PATH = "discord_music_player.infrastructure.discord.cogs.favorites_cog.ensure_voice"


class TestFavoritesAdd:
    @pytest.mark.asyncio
    async def test_add_current_track(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        track = _make_track()
        session = MagicMock()
        session.current_track = track
        container.session_repository.get = AsyncMock(return_value=session)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.favorites_add.callback(cog, interaction)

        container.favorites_repository.add.assert_awaited_once_with(222, track)
        msg = interaction.response.send_message.call_args[0][0]
        assert "Test Song" in msg

    @pytest.mark.asyncio
    async def test_add_nothing_playing(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        session = MagicMock()
        session.current_track = None
        container.session_repository.get = AsyncMock(return_value=session)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.favorites_add.callback(cog, interaction)

        container.favorites_repository.add.assert_not_awaited()
        msg = interaction.response.send_message.call_args[0][0]
        assert "Nothing is playing" in msg

    @pytest.mark.asyncio
    async def test_add_at_limit(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        track = _make_track()
        session = MagicMock()
        session.current_track = track
        container.session_repository.get = AsyncMock(return_value=session)
        container.favorites_repository.add = AsyncMock(return_value=False)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.favorites_add.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "already" in msg or "limit" in msg


# ---------------------------------------------------------------------------
# favorites_list
# ---------------------------------------------------------------------------

class TestFavoritesList:
    @pytest.mark.asyncio
    async def test_list_shows_embed(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(3)]
        container.favorites_repository.get_all = AsyncMock(return_value=tracks)

        await cog.favorites_list.callback(cog, interaction, page=1)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed: discord.Embed = call_kwargs["embed"]
        assert "3 tracks" in embed.title
        assert len(embed.fields) == 3

    @pytest.mark.asyncio
    async def test_list_empty(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.favorites_repository.get_all = AsyncMock(return_value=[])

        await cog.favorites_list.callback(cog, interaction, page=1)

        msg = interaction.response.send_message.call_args[0][0]
        assert "don't have any favorites" in msg


# ---------------------------------------------------------------------------
# favorites_play
# ---------------------------------------------------------------------------

class TestFavoritesPlay:
    @pytest.mark.asyncio
    async def test_play_shuffles_and_enqueues(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(5)]
        container.favorites_repository.get_all = AsyncMock(return_value=tracks)

        batch_result = MagicMock()
        batch_result.enqueued = 5
        batch_result.should_start = True
        container.queue_service.enqueue_batch = AsyncMock(return_value=batch_result)

        with (
            patch(VOICE_PATH, new_callable=AsyncMock, return_value=True),
            patch("random.shuffle"),
        ):
            await cog.favorites_play.callback(cog, interaction)

        container.queue_service.enqueue_batch.assert_awaited_once()
        container.playback_service.start_playback.assert_awaited_once_with(111)
        msg = interaction.followup.send.call_args[0][0]
        assert "5" in msg

    @pytest.mark.asyncio
    async def test_play_empty_favorites(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.favorites_repository.get_all = AsyncMock(return_value=[])

        with patch(VOICE_PATH, new_callable=AsyncMock, return_value=True):
            await cog.favorites_play.callback(cog, interaction)

        container.queue_service.enqueue_batch.assert_not_awaited()
        msg = interaction.followup.send.call_args[0][0]
        assert "don't have any favorites" in msg


# ---------------------------------------------------------------------------
# favorites_remove
# ---------------------------------------------------------------------------

class TestFavoritesRemove:
    @pytest.mark.asyncio
    async def test_remove_by_position(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(3)]
        container.favorites_repository.get_all = AsyncMock(return_value=tracks)
        container.favorites_repository.remove = AsyncMock(return_value=True)

        await cog.favorites_remove.callback(cog, interaction, position=2)

        container.favorites_repository.remove.assert_awaited_once_with(222, "id1")
        msg = interaction.response.send_message.call_args[0][0]
        assert "Removed" in msg
        assert "Song 1" in msg

    @pytest.mark.asyncio
    async def test_remove_invalid_position(
        self, cog: FavoritesCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track("id0", "Song 0")]
        container.favorites_repository.get_all = AsyncMock(return_value=tracks)

        await cog.favorites_remove.callback(cog, interaction, position=5)

        container.favorites_repository.remove.assert_not_awaited()
        msg = interaction.response.send_message.call_args[0][0]
        assert "Invalid position" in msg
