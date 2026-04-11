"""Unit tests for RadioCountView (select menu / timeout behaviour)."""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest


def _make_container() -> MagicMock:
    container = MagicMock()
    container.radio_service = MagicMock()
    container.queue_service = MagicMock()
    container.session_repository = MagicMock()
    container.playback_service = MagicMock()
    return container


def _make_view(
    *,
    start_radio: AsyncMock | None = None,
    query: str | None = None,
    container: MagicMock | None = None,
) -> "RadioCountView":
    from discord_music_player.infrastructure.discord.views.radio_count_view import (
        RadioCountView,
    )

    if container is None:
        container = _make_container()
    return RadioCountView(
        guild_id=123,
        container=container,
        query=query,
        start_radio=start_radio,
    )


@contextmanager
def _select_value(view: object, value: str) -> Generator[None, None, None]:
    """Patch the Select.values property so the view reads the chosen value."""
    select = next(c for c in view.children if isinstance(c, discord.ui.Select))  # type: ignore[attr-defined]
    with patch.object(type(select), "values", new_callable=PropertyMock, return_value=[value]):
        yield


def test_init_creates_select_with_correct_options() -> None:
    view = _make_view()

    selects = [c for c in view.children if isinstance(c, discord.ui.Select)]
    assert len(selects) == 1
    select = selects[0]
    values = [opt.value for opt in select.options]
    assert values == ["3", "5", "10"]
    assert select.placeholder == "How many songs?"


@pytest.mark.asyncio
async def test_on_select_with_callback_calls_start_radio() -> None:
    callback = AsyncMock()
    view = _make_view(start_radio=callback, query="jazz")

    interaction = AsyncMock()
    with _select_value(view, "5"):
        await view._on_select(interaction)

    interaction.response.defer.assert_awaited_once()
    callback.assert_awaited_once_with(interaction, 5, "jazz")


@pytest.mark.asyncio
async def test_on_select_without_callback_falls_back_to_cog() -> None:
    view = _make_view(query="rock")

    from discord_music_player.infrastructure.discord.cogs.radio_cog import RadioCog

    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    mock_cog = MagicMock(spec=RadioCog)
    mock_cog.start_radio = AsyncMock()
    interaction.client.get_cog.return_value = mock_cog

    with _select_value(view, "10"):
        await view._on_select(interaction)

    interaction.response.defer.assert_awaited_once()
    interaction.client.get_cog.assert_called_once_with("RadioCog")
    mock_cog.start_radio.assert_awaited_once_with(interaction, count=10, query="rock")


@pytest.mark.asyncio
async def test_on_select_without_callback_and_no_cog_sends_error() -> None:
    view = _make_view()

    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    interaction.client.get_cog.return_value = None

    with _select_value(view, "3"):
        await view._on_select(interaction)

    interaction.followup.send.assert_awaited_once()
    call_kwargs = interaction.followup.send.call_args
    assert "not available" in call_kwargs[0][0]


@pytest.mark.asyncio
async def test_on_timeout_deletes_message() -> None:
    view = _make_view()
    message = AsyncMock()
    view.set_message(message)

    await view.on_timeout()

    message.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_race_guard_second_select_returns_early() -> None:
    callback = AsyncMock()
    view = _make_view(start_radio=callback)

    interaction1 = AsyncMock()
    interaction2 = AsyncMock()

    with _select_value(view, "5"):
        await view._on_select(interaction1)
        await view._on_select(interaction2)

    # Only the first call should go through
    assert callback.await_count == 1
    interaction2.response.defer.assert_not_awaited()
