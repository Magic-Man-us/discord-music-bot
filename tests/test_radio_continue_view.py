"""Unit tests for RadioContinueView (Continue/Stop/Timeout behaviour)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


def _make_container() -> MagicMock:
    container = MagicMock()
    container.radio_service = MagicMock()
    container.radio_service.continue_radio = AsyncMock()
    container.radio_service.disable_radio = MagicMock()
    container.queue_service = MagicMock()
    container.queue_service.get_queue = AsyncMock()
    container.session_repository = MagicMock()
    container.session_repository.get = AsyncMock(return_value=None)
    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()
    return container


def _make_view(container: MagicMock | None = None) -> "RadioContinueView":
    from discord_music_player.infrastructure.discord.views.radio_continue_view import (
        RadioContinueView,
    )

    if container is None:
        container = _make_container()
    return RadioContinueView(guild_id=123, container=container)


def test_build_continue_embed_contains_track_count() -> None:
    from discord_music_player.infrastructure.discord.views.radio_continue_view import (
        build_continue_embed,
    )

    embed = build_continue_embed(42)

    assert "42" in embed.description
    assert embed.title == "Radio Batch Complete"


@pytest.mark.asyncio
async def test_continue_button_success_creates_radio_view() -> None:
    container = _make_container()

    track = MagicMock()
    track.title = "Song A"
    result = MagicMock()
    result.enabled = True
    result.generated_tracks = [track]
    result.seed_title = "Seed Song"
    result.message = None
    container.radio_service.continue_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    queue_info.total_tracks = 5
    container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    view = _make_view(container)
    interaction = AsyncMock()

    with patch(
        "discord_music_player.infrastructure.discord.views.radio_continue_view.RadioView"
    ) as MockRadioView, patch(
        "discord_music_player.infrastructure.discord.views.radio_continue_view.build_up_next_embed"
    ) as mock_embed_fn:
        mock_embed = MagicMock(spec=discord.Embed)
        mock_embed_fn.return_value = mock_embed
        mock_radio_view = MagicMock()
        MockRadioView.return_value = mock_radio_view

        await view.continue_button.callback(interaction)

        interaction.response.defer.assert_awaited_once()
        container.radio_service.continue_radio.assert_awaited_once_with(123)
        mock_embed_fn.assert_called_once_with([track], "Seed Song")
        interaction.edit_original_response.assert_awaited_once()
        call_kwargs = interaction.edit_original_response.call_args[1]
        assert call_kwargs["embed"] is mock_embed
        assert call_kwargs["view"] is mock_radio_view


@pytest.mark.asyncio
async def test_continue_button_failure_shows_stopped_embed() -> None:
    container = _make_container()

    result = MagicMock()
    result.enabled = False
    result.message = "No seeds available."
    result.generated_tracks = []
    container.radio_service.continue_radio = AsyncMock(return_value=result)

    view = _make_view(container)
    interaction = AsyncMock()

    await view.continue_button.callback(interaction)

    interaction.response.defer.assert_awaited_once()
    call_kwargs = interaction.edit_original_response.call_args[1]
    embed = call_kwargs["embed"]
    assert embed.title == "Radio Stopped"
    assert "No seeds available." in embed.description


@pytest.mark.asyncio
async def test_continue_button_starts_playback_when_idle() -> None:
    container = _make_container()

    track = MagicMock()
    result = MagicMock()
    result.enabled = True
    result.generated_tracks = [track]
    result.seed_title = "Seed"
    container.radio_service.continue_radio = AsyncMock(return_value=result)

    queue_info = MagicMock()
    queue_info.total_tracks = 1
    container.queue_service.get_queue = AsyncMock(return_value=queue_info)

    session = MagicMock()
    session.is_idle = True
    container.session_repository.get = AsyncMock(return_value=session)

    view = _make_view(container)
    interaction = AsyncMock()

    with patch(
        "discord_music_player.infrastructure.discord.views.radio_continue_view.RadioView"
    ), patch(
        "discord_music_player.infrastructure.discord.views.radio_continue_view.build_up_next_embed"
    ) as mock_embed_fn:
        mock_embed_fn.return_value = MagicMock(spec=discord.Embed)
        await view.continue_button.callback(interaction)

    container.session_repository.get.assert_awaited_once_with(123)
    container.playback_service.start_playback.assert_awaited_once_with(123)


@pytest.mark.asyncio
async def test_stop_button_disables_radio_and_edits() -> None:
    container = _make_container()
    view = _make_view(container)
    interaction = AsyncMock()

    await view.stop_button.callback(interaction)

    container.radio_service.disable_radio.assert_called_once_with(123)
    call_kwargs = interaction.response.edit_message.call_args[1]
    embed = call_kwargs["embed"]
    assert embed.title == "Radio Stopped"
    assert "disabled" in embed.description


@pytest.mark.asyncio
async def test_on_timeout_disables_radio_and_deletes_message() -> None:
    container = _make_container()
    view = _make_view(container)
    message = AsyncMock()
    view.set_message(message)

    await view.on_timeout()

    container.radio_service.disable_radio.assert_called_once_with(123)
    message.delete.assert_awaited_once_with(delay=10.0)


@pytest.mark.asyncio
async def test_race_guard_second_press_returns_early() -> None:
    container = _make_container()
    result = MagicMock()
    result.enabled = False
    result.message = "stopped"
    result.generated_tracks = []
    container.radio_service.continue_radio = AsyncMock(return_value=result)

    view = _make_view(container)
    interaction1 = AsyncMock()
    interaction2 = AsyncMock()

    await view.continue_button.callback(interaction1)
    await view.continue_button.callback(interaction2)

    # Only the first interaction should have been processed
    assert container.radio_service.continue_radio.await_count == 1
    interaction2.response.defer.assert_not_awaited()
