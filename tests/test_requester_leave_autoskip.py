"""Unit tests for requester-leave pause-and-prompt subscriber."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import TrackId
from discord_music_player.domain.shared.events import (
    VoiceMemberLeftVoiceChannel,
    get_event_bus,
    reset_event_bus,
)


def _make_subscriber(
    *,
    session_repo: AsyncMock | None = None,
    playback_service: AsyncMock | None = None,
    voice_adapter: AsyncMock | None = None,
):
    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    session_repo = session_repo or AsyncMock()
    playback_service = playback_service or AsyncMock()
    voice_adapter = voice_adapter or AsyncMock()
    return AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )


def _make_session_with_track(
    guild_id: int = 123,
    track_id: str = "t1",
    title: str = "Song",
    requested_by_id: int | None = 42,
) -> GuildPlaybackSession:
    session = GuildPlaybackSession(guild_id=guild_id)
    session.current_track = Track(
        id=TrackId(track_id),
        title=title,
        webpage_url="https://example.com",
        requested_by_id=requested_by_id,
    )
    return session


# === Pause + Callback Tests ===


@pytest.mark.asyncio
async def test_requester_leave_pauses_and_invokes_callback() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track()
    session_repo.get.return_value = session
    playback_service.pause_playback.return_value = True
    voice_adapter.get_listeners.return_value = [100, 200]

    callback = AsyncMock()

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.set_on_requester_left_callback(callback)
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_awaited_once_with(123)
    playback_service.skip_track.assert_not_called()
    callback.assert_awaited_once_with(123, 42, session.current_track)


@pytest.mark.asyncio
async def test_requester_leave_no_callback_still_pauses() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track()
    session_repo.get.return_value = session
    playback_service.pause_playback.return_value = True
    voice_adapter.get_listeners.return_value = [100]

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_awaited_once_with(123)
    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_no_callback_when_pause_fails() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track()
    session_repo.get.return_value = session
    playback_service.pause_playback.return_value = False
    voice_adapter.get_listeners.return_value = [100]

    callback = AsyncMock()

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.set_on_requester_left_callback(callback)
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_awaited_once_with(123)
    callback.assert_not_called()


# === No-Listeners Edge Case ===


@pytest.mark.asyncio
async def test_skip_immediately_when_no_listeners() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track()
    session_repo.get.return_value = session
    voice_adapter.get_listeners.return_value = []

    callback = AsyncMock()

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.set_on_requester_left_callback(callback)
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.skip_track.assert_awaited_once_with(123)
    playback_service.pause_playback.assert_not_called()
    callback.assert_not_called()


# === Guard Clause Tests (unchanged behavior) ===


@pytest.mark.asyncio
async def test_non_requester_leave_noop() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track()
    session_repo.get.return_value = session

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=777))

    playback_service.pause_playback.assert_not_called()
    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_start_when_already_started_is_noop() -> None:
    reset_event_bus()

    subscriber = _make_subscriber()
    subscriber.start()
    subscriber.start()

    assert subscriber._started is True


@pytest.mark.asyncio
async def test_stop_when_not_started_is_noop() -> None:
    reset_event_bus()

    subscriber = _make_subscriber()
    subscriber.stop()

    assert subscriber._started is False


@pytest.mark.asyncio
async def test_stop_after_start() -> None:
    reset_event_bus()

    subscriber = _make_subscriber()
    subscriber.start()
    subscriber.stop()

    assert subscriber._started is False


@pytest.mark.asyncio
async def test_no_session_does_not_act() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session_repo.get.return_value = None

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_not_called()
    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_no_current_track_does_not_act() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = None
    session_repo.get.return_value = session

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_not_called()
    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_no_requester_id_does_not_act() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()
    voice_adapter = AsyncMock()

    session = _make_session_with_track(requested_by_id=None)
    session_repo.get.return_value = session

    subscriber = _make_subscriber(
        session_repo=session_repo,
        playback_service=playback_service,
        voice_adapter=voice_adapter,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.pause_playback.assert_not_called()
    playback_service.skip_track.assert_not_called()
