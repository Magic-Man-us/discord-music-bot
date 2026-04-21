"""Unit tests for the post-import "save playlist?" prompt View."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.infrastructure.discord.views.save_playlist_prompt_view import (
    SavePlaylistPromptView,
)


@pytest.fixture(autouse=True)
def mock_discord_event_loop():
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    loop.create_future.return_value = MagicMock()
    with patch("asyncio.get_running_loop", return_value=loop):
        yield loop


def _make_interaction(user_id: int = 42) -> AsyncMock:
    interaction = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "Tester"
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 111
    return interaction


def _make_view(
    *,
    requester_id: int = 42,
    suggested_name: str = "my-mix",
) -> SavePlaylistPromptView:
    container = MagicMock()
    container.saved_queue_repository = MagicMock()
    container.saved_queue_repository.save = AsyncMock(return_value=True)
    tracks = [MagicMock()]
    return SavePlaylistPromptView(
        container=container,
        tracks=tracks,
        suggested_name=suggested_name,
        requester_id=requester_id,
    )


class TestInteractionCheck:
    @pytest.mark.asyncio
    async def test_blocks_other_user(self) -> None:
        view = _make_view(requester_id=42)
        interaction = _make_interaction(user_id=99)

        allowed = await view.interaction_check(interaction)

        assert allowed is False
        interaction.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_allows_requester(self) -> None:
        view = _make_view(requester_id=42)
        interaction = _make_interaction(user_id=42)

        allowed = await view.interaction_check(interaction)

        assert allowed is True


class TestDismissButton:
    @pytest.mark.asyncio
    async def test_edits_message_and_disables(self) -> None:
        view = _make_view()
        interaction = _make_interaction()

        await view.dismiss_button.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        kwargs = interaction.response.edit_message.call_args[1]
        assert "not saving" in kwargs["content"].lower()


class TestSaveButton:
    @pytest.mark.asyncio
    async def test_opens_modal_with_suggested_name(self) -> None:
        view = _make_view(suggested_name="chill-vibes")
        interaction = _make_interaction()

        await view.save_button.callback(interaction)

        interaction.response.send_modal.assert_awaited_once()
        modal = interaction.response.send_modal.call_args.args[0]
        assert modal.name_input.default == "chill-vibes"
