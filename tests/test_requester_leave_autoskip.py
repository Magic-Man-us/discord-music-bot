"""Unit tests for requester-leave auto-skip subscriber."""

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


@pytest.mark.asyncio
async def test_auto_skip_on_requester_leave_triggers_skip() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = Track(
        id=TrackId("t1"),
        title="Song",
        webpage_url="https://example.com",
        requested_by_id=42,
    )
    session_repo.get.return_value = session
    playback_service.skip_track.return_value = session.current_track

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.skip_track.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_auto_skip_on_non_requester_leave_noop() -> None:
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = Track(
        id=TrackId("t1"),
        title="Song",
        webpage_url="https://example.com",
        requested_by_id=42,
    )
    session_repo.get.return_value = session

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=777))

    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_start_when_already_started_is_noop() -> None:
    """Should not re-subscribe if already started."""
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )

    # Start twice
    subscriber.start()
    subscriber.start()

    # Should still only have one handler registered
    assert subscriber._started is True


@pytest.mark.asyncio
async def test_stop_when_not_started_is_noop() -> None:
    """Should handle stop when not started."""
    reset_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )

    # Stop without starting
    subscriber.stop()

    assert subscriber._started is False


@pytest.mark.asyncio
async def test_stop_after_start() -> None:
    """Should unsubscribe after stopping."""
    reset_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )

    subscriber.start()
    subscriber.stop()

    assert subscriber._started is False


@pytest.mark.asyncio
async def test_no_session_does_not_skip() -> None:
    """Should not skip when no session exists."""
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    # No session
    session_repo.get.return_value = None

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_no_current_track_does_not_skip() -> None:
    """Should not skip when no track is playing."""
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = None  # No current track
    session_repo.get.return_value = session

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_no_requester_id_does_not_skip() -> None:
    """Should not skip when track has no requester."""
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = Track(
        id=TrackId("t1"),
        title="Song",
        webpage_url="https://example.com",
        requested_by_id=None,  # No requester
    )
    session_repo.get.return_value = session

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    playback_service.skip_track.assert_not_called()


@pytest.mark.asyncio
async def test_skip_returns_none_logs_only() -> None:
    """Should handle when skip returns None (no track to skip)."""
    reset_event_bus()
    bus = get_event_bus()

    session_repo = AsyncMock()
    playback_service = AsyncMock()

    session = GuildPlaybackSession(guild_id=123)
    session.current_track = Track(
        id=TrackId("t1"),
        title="Song",
        webpage_url="https://example.com",
        requested_by_id=42,
    )
    session_repo.get.return_value = session
    playback_service.skip_track.return_value = None  # Skip returned None

    from discord_music_player.application.services.requester_leave_autoskip import (
        AutoSkipOnRequesterLeave,
    )

    subscriber = AutoSkipOnRequesterLeave(
        session_repository=session_repo,
        playback_service=playback_service,
    )
    subscriber.start()

    await bus.publish(VoiceMemberLeftVoiceChannel(guild_id=123, channel_id=999, user_id=42))

    # Should have tried to skip but got None back
    playback_service.skip_track.assert_awaited_once_with(123)
