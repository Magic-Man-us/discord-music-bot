"""Tests for QueueCog — shuffle_history and uncovered branches."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.infrastructure.discord.cogs.queue_cog import QueueCog

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_container():
    container = MagicMock()
    container.voice_warmup_tracker = MagicMock()
    container.voice_warmup_tracker.remaining_seconds.return_value = 0

    container.voice_adapter = MagicMock()
    container.voice_adapter.is_connected = MagicMock(return_value=True)
    container.voice_adapter.ensure_connected = AsyncMock(return_value=True)

    container.queue_service = MagicMock()
    container.queue_service.enqueue = AsyncMock()
    container.queue_service.enqueue_batch = AsyncMock()
    container.queue_service.get_queue = AsyncMock()
    container.queue_service.shuffle = AsyncMock()
    container.queue_service.remove = AsyncMock()
    container.queue_service.clear = AsyncMock()
    container.queue_service.toggle_loop = AsyncMock()

    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()

    container.history_repository = MagicMock()
    container.history_repository.get_recent = AsyncMock()

    container.message_state_manager = MagicMock()
    container.message_state_manager.reset = AsyncMock()

    return container


@pytest.fixture
def cog(mock_container):
    bot = MagicMock()
    return QueueCog(bot, mock_container)


@pytest.fixture
def interaction():
    i = MagicMock(spec=discord.Interaction)
    i.response = MagicMock()
    i.response.is_done.return_value = False
    i.response.send_message = AsyncMock()
    i.response.defer = AsyncMock()
    i.followup = MagicMock()
    i.followup.send = AsyncMock()

    i.guild = MagicMock()
    i.guild.id = 111

    member = MagicMock(spec=discord.Member)
    member.id = 222
    member.display_name = "TestUser"
    member.name = "testuser"
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 333
    i.user = member
    return i


def _track(track_id: str = "t1") -> MagicMock:
    t = MagicMock()
    t.id = MagicMock()
    t.id.value = track_id
    t.title = f"Track {track_id}"
    t.duration_seconds = 180
    t.requested_by_id = 222
    t.requested_by_name = "TestUser"
    return t


# =============================================================================
# shuffle_history
# =============================================================================


@pytest.mark.asyncio
async def test_shuffle_history_success(cog, interaction, mock_container):
    tracks = [_track("t1"), _track("t2"), _track("t3")]
    mock_container.history_repository.get_recent = AsyncMock(return_value=tracks)

    batch_result = MagicMock()
    batch_result.enqueued = 3
    batch_result.should_start = True
    mock_container.queue_service.enqueue_batch = AsyncMock(return_value=batch_result)

    with patch("random.shuffle"):
        await cog.shuffle_history.callback(cog, interaction, limit=100)

    mock_container.queue_service.enqueue_batch.assert_awaited_once()
    mock_container.playback_service.start_playback.assert_awaited_once_with(111)
    msg = interaction.followup.send.call_args[0][0]
    assert "3" in msg


@pytest.mark.asyncio
async def test_shuffle_history_no_history(cog, interaction, mock_container):
    mock_container.history_repository.get_recent = AsyncMock(return_value=[])

    await cog.shuffle_history.callback(cog, interaction, limit=100)

    msg = interaction.followup.send.call_args[0][0]
    assert msg == "No tracks have been played yet in this server."


@pytest.mark.asyncio
async def test_shuffle_history_deduplicates(cog, interaction, mock_container):
    # Same track_id appears 3 times — dedup yields 1 unique track
    tracks = [_track("t1"), _track("t1"), _track("t1")]
    mock_container.history_repository.get_recent = AsyncMock(return_value=tracks)

    batch_result = MagicMock()
    batch_result.enqueued = 1
    batch_result.should_start = False
    mock_container.queue_service.enqueue_batch = AsyncMock(return_value=batch_result)

    await cog.shuffle_history.callback(cog, interaction, limit=100)

    # enqueue_batch called with 1 unique track
    call_args = mock_container.queue_service.enqueue_batch.call_args
    assert len(call_args.kwargs["tracks"]) == 1
    msg = interaction.followup.send.call_args[0][0]
    assert "1" in msg


# =============================================================================
# queue with total_duration
# =============================================================================


@pytest.mark.asyncio
async def test_queue_with_total_duration_shows_footer(cog, interaction, mock_container):
    track = _track("t1")
    queue_info = MagicMock()
    queue_info.total_tracks = 1
    queue_info.current_track = None
    queue_info.tracks = [track]
    queue_info.total_duration = 360
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.queue.callback(cog, interaction, page=1)

    call_args = interaction.response.send_message.call_args
    embed = call_args[1]["embed"]
    assert embed.footer is not None
    assert "Total duration" in embed.footer.text


@pytest.mark.asyncio
async def test_queue_without_total_duration_no_footer(cog, interaction, mock_container):
    track = _track("t1")
    queue_info = MagicMock()
    queue_info.total_tracks = 1
    queue_info.current_track = None
    queue_info.tracks = [track]
    queue_info.total_duration = None
    mock_container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    await cog.queue.callback(cog, interaction, page=1)

    call_args = interaction.response.send_message.call_args
    embed = call_args[1]["embed"]
    assert (
        embed.footer.text is discord.utils.MISSING
        or embed.footer is None
        or "Total duration" not in str(embed.footer)
    )


# =============================================================================
# setup()
# =============================================================================


@pytest.mark.asyncio
async def test_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.queue_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


# =============================================================================
# Voice-guard rejection paths and command-body branches not in the original
# tests. Uses Discord stubs from conftest.py for cleaner setup.
# =============================================================================


from conftest import (  # noqa: E402  -- pytest adds tests/ to sys.path
    FakeContainer,
    FakeVoiceAdapter,
    FakeVoiceWarmupTracker,
    make_interaction,
    make_member,
    make_voice_channel,
    make_voice_state,
)
from discord_music_player.application.services.queue_models import QueueSnapshot
from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.enums import LoopMode
from discord_music_player.domain.music.wrappers import TrackId


def _real_track(track_id: str = "t1", **overrides) -> Track:
    base = dict(
        id=TrackId(value=track_id),
        title=f"T-{track_id}",
        webpage_url=f"https://yt/{track_id}",
        duration_seconds=180,
        artist="Artist",
        uploader="Uploader",
        requested_by_id=999,
        requested_by_name="Req",
    )
    base.update(overrides)
    return Track(**base)


def _interaction_in_voice():
    member = make_member(member_id=1)
    member.voice = make_voice_state(channel=make_voice_channel(channel_id=10, members=[member]))
    return make_interaction(user=member, guild_id=42)


def _stub_container(
    *,
    queue_snapshot=None,
    shuffle_returns=True,
    remove_returns=None,
    move_returns=True,
    clear_returns=0,
    toggle_loop_returns=LoopMode.OFF,
    recent_by_user=None,
    dj_role_id=None,
):
    queue_service = MagicMock()
    queue_service.get_queue = AsyncMock(return_value=queue_snapshot)
    queue_service.shuffle = AsyncMock(return_value=shuffle_returns)
    queue_service.remove = AsyncMock(return_value=remove_returns)
    queue_service.move = AsyncMock(return_value=move_returns)
    queue_service.clear = AsyncMock(return_value=clear_returns)
    queue_service.toggle_loop = AsyncMock(return_value=toggle_loop_returns)
    queue_service.enqueue_batch = AsyncMock(return_value=MagicMock(enqueued=len(recent_by_user or []), should_start=False))

    history_repository = MagicMock()
    history_repository.get_recent_by_user = AsyncMock(return_value=recent_by_user or [])

    settings = MagicMock()
    settings.discord.dj_role_id = dj_role_id

    message_state_manager = MagicMock()
    message_state_manager.reset = AsyncMock()
    message_state_manager.reserve_now_playing = MagicMock()

    playback_service = MagicMock()
    playback_service.start_playback = AsyncMock()

    return FakeContainer(
        voice_warmup_tracker=FakeVoiceWarmupTracker(remaining=0),
        voice_adapter=FakeVoiceAdapter(connected=True),
        queue_service=queue_service,
        history_repository=history_repository,
        settings=settings,
        message_state_manager=message_state_manager,
        playback_service=playback_service,
    )


def _make_cog(container) -> QueueCog:
    return QueueCog(MagicMock(), container)


# --- voice-guard rejection paths ----------------------------------------


class TestVoiceGuardRejections:
    @pytest.mark.asyncio
    async def test_queue_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.queue.callback(cog, i, page=1)
        cog.container.queue_service.get_queue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shuffle_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.shuffle.callback(cog, i)
        cog.container.queue_service.shuffle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_shuffle_history_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.shuffle_history.callback(cog, i, limit=10)
        # The historic ensure_voice path should reject before touching repo
        cog.container.queue_service.enqueue_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_loop_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.loop.callback(cog, i)
        cog.container.queue_service.toggle_loop.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_remove_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.remove.callback(cog, i, position=1)
        cog.container.queue_service.remove.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_move_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.move.callback(cog, i, from_position=1, to_position=2)
        cog.container.queue_service.move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clear_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        cog = _make_cog(_stub_container())
        await cog.clear.callback(cog, i)
        cog.container.queue_service.clear.assert_not_awaited()


# --- /queue branch where current track lacks artist/uploader ------------


class TestQueueArtistFallback:
    @pytest.mark.asyncio
    async def test_renders_when_no_artist_or_uploader(self):
        i = _interaction_in_voice()
        snap = QueueSnapshot(
            current_track=_real_track("cur", artist=None, uploader=None),
            tracks=[],
            total_tracks=1,
            total_duration=180,
        )
        cog = _make_cog(_stub_container(queue_snapshot=snap))
        await cog.queue.callback(cog, i, page=1)
        assert "embed" in i.response.send_message.call_args.kwargs


# --- /shuffle success/failure paths -------------------------------------


class TestShuffleResultMessages:
    @pytest.mark.asyncio
    async def test_shuffle_success_message(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(shuffle_returns=True))
        await cog.shuffle.callback(cog, i)
        assert i.response.send_message.call_args.args[0] == "Shuffled the queue."

    @pytest.mark.asyncio
    async def test_shuffle_not_enough_tracks_message(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(shuffle_returns=False))
        await cog.shuffle.callback(cog, i)
        assert "Not enough" in i.response.send_message.call_args.args[0]


# --- /shuffle_user_history --------------------------------------------------


class TestShuffleUserHistory:
    @pytest.mark.asyncio
    async def test_voice_guard_fail(self):
        i = make_interaction(user=make_member(voice=None))
        target = make_member(member_id=999)
        cog = _make_cog(_stub_container())
        await cog.shuffle_user_history.callback(cog, i, user=target, limit=10)
        cog.container.history_repository.get_recent_by_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_history_for_user(self):
        i = _interaction_in_voice()
        target = make_member(member_id=999)
        target.display_name = "Alice"
        cog = _make_cog(_stub_container(recent_by_user=[]))
        await cog.shuffle_user_history.callback(cog, i, user=target, limit=10)
        msg = i.followup.send.call_args.args[0]
        assert "Alice" in msg

    @pytest.mark.asyncio
    async def test_success_enqueues_shuffled_tracks(self):
        i = _interaction_in_voice()
        target = make_member(member_id=999)
        target.display_name = "Bob"
        tracks = [_real_track(f"u{i}") for i in range(3)]
        cog = _make_cog(_stub_container(recent_by_user=tracks))
        cog.enqueue_and_start = AsyncMock(return_value=MagicMock(enqueued=3))
        await cog.shuffle_user_history.callback(cog, i, user=target, limit=10)
        msg = i.followup.send.call_args.args[0]
        assert "Bob" in msg
        assert "3" in msg


# --- /loop output -------------------------------------------------------


class TestLoopMode:
    @pytest.mark.asyncio
    async def test_returns_mode_label(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(toggle_loop_returns=LoopMode.QUEUE))
        await cog.loop.callback(cog, i)
        assert "queue" in i.response.send_message.call_args.args[0].lower()


# --- /remove ------------------------------------------------------------


class TestRemoveOutcomes:
    @pytest.mark.asyncio
    async def test_success(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(remove_returns=_real_track("rm")))
        await cog.remove.callback(cog, i, position=1)
        assert "Removed" in i.response.send_message.call_args.args[0]

    @pytest.mark.asyncio
    async def test_position_not_found(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(remove_returns=None))
        await cog.remove.callback(cog, i, position=99)
        assert "No track at position 99" in i.response.send_message.call_args.args[0]


# --- /move --------------------------------------------------------------


class TestMoveOutcomes:
    @pytest.mark.asyncio
    async def test_success(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(move_returns=True))
        await cog.move.callback(cog, i, from_position=2, to_position=5)
        assert "Moved track from position 2 to 5" in i.response.send_message.call_args.args[0]

    @pytest.mark.asyncio
    async def test_invalid_positions(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(move_returns=False))
        await cog.move.callback(cog, i, from_position=99, to_position=100)
        assert "Invalid position" in i.response.send_message.call_args.args[0]


# --- /clear -------------------------------------------------------------


class TestClearOutcomes:
    @pytest.mark.asyncio
    async def test_dj_role_required_blocks_non_dj(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(dj_role_id=500, clear_returns=5))
        await cog.clear.callback(cog, i)
        cog.container.queue_service.clear.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_clears_when_tracks_present(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(clear_returns=3))
        await cog.clear.callback(cog, i)
        assert "Cleared 3" in i.response.send_message.call_args.args[0]
        cog.container.message_state_manager.reset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_empty_message(self):
        i = _interaction_in_voice()
        cog = _make_cog(_stub_container(clear_returns=0))
        await cog.clear.callback(cog, i)
        assert "already empty" in i.response.send_message.call_args.args[0]
