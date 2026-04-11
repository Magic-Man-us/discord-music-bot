"""Unit tests for SavedQueueCog slash commands."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.infrastructure.discord.cogs.saved_queue_cog import SavedQueueCog


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
    container.saved_queue_repository = MagicMock()
    container.saved_queue_repository.save = AsyncMock(return_value=True)
    container.saved_queue_repository.get = AsyncMock(return_value=None)
    container.saved_queue_repository.list_all = AsyncMock(return_value=[])
    container.saved_queue_repository.delete = AsyncMock(return_value=True)
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
def cog(container: MagicMock) -> SavedQueueCog:
    bot = MagicMock()
    return SavedQueueCog(bot=bot, container=container)


@pytest.fixture
def interaction() -> MagicMock:
    return _make_interaction()


GUARD_PATH = "discord_music_player.infrastructure.discord.cogs.saved_queue_cog.ensure_user_in_voice_and_warm"
VOICE_PATH = "discord_music_player.infrastructure.discord.cogs.saved_queue_cog.ensure_voice"


# ---------------------------------------------------------------------------
# save_queue
# ---------------------------------------------------------------------------

class TestSaveQueue:
    @pytest.mark.asyncio
    async def test_save_current_queue(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(3)]
        session = MagicMock()
        session.has_tracks = True
        session.current_track = tracks[0]
        session.queue = tracks[1:]
        container.session_repository.get = AsyncMock(return_value=session)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.save_queue.callback(cog, interaction, name="my playlist")

        container.saved_queue_repository.save.assert_awaited_once()
        call_kwargs = container.saved_queue_repository.save.call_args[1]
        assert call_kwargs["name"] == "my playlist"
        assert len(call_kwargs["tracks"]) == 3
        msg = interaction.response.send_message.call_args[0][0]
        assert "3" in msg
        assert "my playlist" in msg

    @pytest.mark.asyncio
    async def test_save_empty_queue(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        session = MagicMock()
        session.has_tracks = False
        container.session_repository.get = AsyncMock(return_value=session)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.save_queue.callback(cog, interaction, name="empty")

        container.saved_queue_repository.save.assert_not_awaited()
        msg = interaction.response.send_message.call_args[0][0]
        assert "empty" in msg.lower() or "Nothing to save" in msg

    @pytest.mark.asyncio
    async def test_save_at_limit(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        session = MagicMock()
        session.has_tracks = True
        session.current_track = _make_track()
        session.queue = []
        container.session_repository.get = AsyncMock(return_value=session)
        container.saved_queue_repository.save = AsyncMock(return_value=False)

        with patch(GUARD_PATH, new_callable=AsyncMock, return_value=True):
            await cog.save_queue.callback(cog, interaction, name="overflow")

        msg = interaction.response.send_message.call_args[0][0]
        assert "Too many" in msg or "Delete" in msg


# ---------------------------------------------------------------------------
# load_queue
# ---------------------------------------------------------------------------

class TestLoadQueue:
    @pytest.mark.asyncio
    async def test_load_enqueues_tracks(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(4)]
        saved = MagicMock()
        saved.to_tracks.return_value = list(tracks)
        container.saved_queue_repository.get = AsyncMock(return_value=saved)

        batch_result = MagicMock()
        batch_result.enqueued = 4
        batch_result.should_start = True
        container.queue_service.enqueue_batch = AsyncMock(return_value=batch_result)

        with patch(VOICE_PATH, new_callable=AsyncMock, return_value=True):
            await cog.load_queue.callback(cog, interaction, name="my playlist", shuffle=False)

        container.queue_service.enqueue_batch.assert_awaited_once()
        container.playback_service.start_playback.assert_awaited_once_with(111)
        msg = interaction.followup.send.call_args[0][0]
        assert "4" in msg
        assert "my playlist" in msg

    @pytest.mark.asyncio
    async def test_load_not_found(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.saved_queue_repository.get = AsyncMock(return_value=None)

        with patch(VOICE_PATH, new_callable=AsyncMock, return_value=True):
            await cog.load_queue.callback(cog, interaction, name="nope", shuffle=False)

        container.queue_service.enqueue_batch.assert_not_awaited()
        msg = interaction.followup.send.call_args[0][0]
        assert "No playlist named" in msg

    @pytest.mark.asyncio
    async def test_load_with_shuffle(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        tracks = [_make_track(f"id{i}", f"Song {i}") for i in range(3)]
        saved = MagicMock()
        saved.to_tracks.return_value = list(tracks)
        container.saved_queue_repository.get = AsyncMock(return_value=saved)

        batch_result = MagicMock()
        batch_result.enqueued = 3
        batch_result.should_start = False
        container.queue_service.enqueue_batch = AsyncMock(return_value=batch_result)

        with (
            patch(VOICE_PATH, new_callable=AsyncMock, return_value=True),
            patch("discord_music_player.infrastructure.discord.cogs.saved_queue_cog.random.shuffle") as mock_shuffle,
        ):
            await cog.load_queue.callback(cog, interaction, name="mix", shuffle=True)

        mock_shuffle.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        assert "shuffled" in msg


# ---------------------------------------------------------------------------
# list_queues
# ---------------------------------------------------------------------------

class TestListQueues:
    @pytest.mark.asyncio
    async def test_list_shows_embed(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        q1 = MagicMock()
        q1.name = "chill"
        q1.track_count = 5
        q1.created_by_name = "Alice"
        q2 = MagicMock()
        q2.name = "hype"
        q2.track_count = 10
        q2.created_by_name = "Bob"
        container.saved_queue_repository.list_all = AsyncMock(return_value=[q1, q2])

        await cog.list_queues.callback(cog, interaction)

        call_kwargs = interaction.response.send_message.call_args[1]
        embed: discord.Embed = call_kwargs["embed"]
        assert "2" in embed.title
        assert len(embed.fields) == 2

    @pytest.mark.asyncio
    async def test_list_empty(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.saved_queue_repository.list_all = AsyncMock(return_value=[])

        await cog.list_queues.callback(cog, interaction)

        msg = interaction.response.send_message.call_args[0][0]
        assert "No saved playlists" in msg


# ---------------------------------------------------------------------------
# delete_queue
# ---------------------------------------------------------------------------

class TestDeleteQueue:
    @pytest.mark.asyncio
    async def test_delete_success(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.saved_queue_repository.delete = AsyncMock(return_value=True)

        await cog.delete_queue.callback(cog, interaction, name="old")

        container.saved_queue_repository.delete.assert_awaited_once_with(111, "old")
        msg = interaction.response.send_message.call_args[0][0]
        assert "Deleted" in msg

    @pytest.mark.asyncio
    async def test_delete_not_found(
        self, cog: SavedQueueCog, interaction: MagicMock, container: MagicMock
    ) -> None:
        container.saved_queue_repository.delete = AsyncMock(return_value=False)

        await cog.delete_queue.callback(cog, interaction, name="nope")

        msg = interaction.response.send_message.call_args[0][0]
        assert "No playlist named" in msg
