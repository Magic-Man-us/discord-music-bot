"""Unit tests for RequesterLeftView (Yes/No/Timeout behaviour)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from discord_music_player.domain.shared.messages import DiscordUIMessages


def _make_view(playback_service: AsyncMock):
    from discord_music_player.infrastructure.discord.views.requester_left_view import (
        RequesterLeftView,
    )

    return RequesterLeftView(
        guild_id=123,
        playback_service=playback_service,
        track_title="Test Song",
        requester_name="<@42>",
    )


@pytest.mark.asyncio
async def test_yes_button_resumes_playback() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    interaction = AsyncMock()

    await view.yes_button.callback(interaction)

    playback_service.resume_playback.assert_awaited_once_with(123)
    playback_service.skip_track.assert_not_called()
    interaction.response.edit_message.assert_awaited_once()
    call_kwargs = interaction.response.edit_message.call_args[1]
    assert call_kwargs["content"] == DiscordUIMessages.REQUESTER_LEFT_RESUMED


@pytest.mark.asyncio
async def test_no_button_skips_track() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    interaction = AsyncMock()

    await view.no_button.callback(interaction)

    playback_service.skip_track.assert_awaited_once_with(123)
    playback_service.resume_playback.assert_not_called()
    interaction.response.edit_message.assert_awaited_once()
    call_kwargs = interaction.response.edit_message.call_args[1]
    assert call_kwargs["content"] == DiscordUIMessages.REQUESTER_LEFT_SKIPPED


@pytest.mark.asyncio
async def test_timeout_skips_track() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    message = AsyncMock()
    view.set_message(message)

    await view.on_timeout()

    playback_service.skip_track.assert_awaited_once_with(123)
    message.edit.assert_awaited_once()
    call_kwargs = message.edit.call_args[1]
    assert call_kwargs["content"] == DiscordUIMessages.REQUESTER_LEFT_TIMEOUT


@pytest.mark.asyncio
async def test_buttons_disabled_after_yes() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    interaction = AsyncMock()

    await view.yes_button.callback(interaction)

    for item in view.children:
        assert item.disabled is True


@pytest.mark.asyncio
async def test_buttons_disabled_after_no() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    interaction = AsyncMock()

    await view.no_button.callback(interaction)

    for item in view.children:
        assert item.disabled is True


@pytest.mark.asyncio
async def test_buttons_disabled_after_timeout() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    message = AsyncMock()
    view.set_message(message)

    await view.on_timeout()

    for item in view.children:
        assert item.disabled is True


@pytest.mark.asyncio
async def test_timeout_without_message_does_not_raise() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)

    await view.on_timeout()

    playback_service.skip_track.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_view_timeout_is_30_seconds() -> None:
    playback_service = AsyncMock()
    view = _make_view(playback_service)
    assert view.timeout == 30.0
