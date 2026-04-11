"""Unit tests for PlaylistView and helper functions."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.shared.constants import (
    DiscordEmbedLimits,
    PlaylistConstants,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def mock_discord_event_loop():
    """Mock the event loop for Discord UI views."""
    loop = MagicMock(spec=asyncio.AbstractEventLoop)
    future = MagicMock()
    loop.create_future.return_value = future
    with patch("asyncio.get_running_loop", return_value=loop):
        yield loop


def _make_entry(
    title: str = "Test Song",
    url: str = "https://www.youtube.com/watch?v=abc123",
    duration_seconds: int | None = 180,
) -> MagicMock:
    entry = MagicMock()
    entry.title = title
    entry.url = url
    entry.duration_seconds = duration_seconds
    return entry


def _make_container() -> MagicMock:
    container = MagicMock()
    container.audio_resolver = MagicMock()
    container.audio_resolver.resolve = AsyncMock(return_value=None)
    container.queue_service = MagicMock()
    enqueue_result = MagicMock()
    enqueue_result.success = True
    enqueue_result.should_start = False
    container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)
    container.voice_adapter = MagicMock()
    container.voice_adapter.is_connected = MagicMock(return_value=False)
    container.voice_adapter.ensure_connected = AsyncMock(return_value=True)
    container.playback_service = MagicMock()
    container.playback_service.start_playback = AsyncMock()
    return container


def _make_interaction(user_id: int = 42) -> AsyncMock:
    interaction = AsyncMock()
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "TestUser"
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.id = 123
    member = MagicMock(spec=discord.Member)
    member.voice = MagicMock()
    member.voice.channel = MagicMock()
    member.voice.channel.id = 456
    interaction.guild.get_member = MagicMock(return_value=member)
    return interaction


def _make_view(
    entries: list[MagicMock] | None = None,
    user_id: int = 42,
    container: MagicMock | None = None,
):
    from discord_music_player.infrastructure.discord.views.playlist_view import (
        PlaylistView,
    )

    if entries is None:
        entries = [_make_entry(title=f"Song {i}") for i in range(3)]
    if container is None:
        container = _make_container()

    init_interaction = MagicMock()
    init_interaction.user = MagicMock()
    init_interaction.user.id = user_id

    view = PlaylistView(entries=entries, interaction=init_interaction, container=container)
    return view, container


# =============================================================================
# build_playlist_embed Tests
# =============================================================================


class TestBuildPlaylistEmbed:
    def test_basic_embed_with_few_entries(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            build_playlist_embed,
        )

        entries = [_make_entry(title=f"Track {i}", duration_seconds=120) for i in range(3)]
        embed = build_playlist_embed(entries)

        assert embed.title == "Playlist Preview"
        assert "3" in embed.description
        assert len(embed.fields) >= 1
        assert embed.fields[0].name == "Tracks"
        assert "Track 0" in embed.fields[0].value

    def test_pagination_into_multiple_fields(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            build_playlist_embed,
        )

        # Create entries with long titles to force multiple fields
        long_title = "A" * 55
        entries = [
            _make_entry(title=f"{long_title} {i}", duration_seconds=60)
            for i in range(PlaylistConstants.MAX_PLAYLIST_TRACKS)
        ]
        embed = build_playlist_embed(entries)

        # With 50 long entries, we should get multiple fields
        assert len(embed.fields) > 1
        # Second field should have "(2)" in the name
        assert "(2)" in embed.fields[1].name

    def test_footer_when_entries_exceed_max(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            build_playlist_embed,
        )

        total = PlaylistConstants.MAX_PLAYLIST_TRACKS + 10
        entries = [_make_entry(title=f"Track {i}") for i in range(total)]
        embed = build_playlist_embed(entries)

        assert embed.footer is not None
        assert str(PlaylistConstants.MAX_PLAYLIST_TRACKS) in embed.footer.text
        assert str(total) in embed.footer.text

    def test_no_footer_when_entries_within_max(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            build_playlist_embed,
        )

        entries = [_make_entry(title=f"Track {i}") for i in range(5)]
        embed = build_playlist_embed(entries)

        assert embed.footer is None or embed.footer.text is None

    def test_unknown_duration_shows_question_mark(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            build_playlist_embed,
        )

        entries = [_make_entry(title="No Duration", duration_seconds=None)]
        embed = build_playlist_embed(entries)

        assert "[?]" in embed.fields[0].value


# =============================================================================
# _build_select_options Tests
# =============================================================================


class TestBuildSelectOptions:
    def test_correct_labels_and_values(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            _build_select_options,
        )

        entries = [
            _make_entry(title="First Song", duration_seconds=90),
            _make_entry(title="Second Song", duration_seconds=200),
        ]
        options = _build_select_options(entries)

        assert len(options) == 2
        assert options[0].label == "First Song"
        assert options[0].value == "0"
        assert options[1].label == "Second Song"
        assert options[1].value == "1"

    def test_description_is_duration_or_none(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            _build_select_options,
        )

        entries = [
            _make_entry(title="Has Duration", duration_seconds=120),
            _make_entry(title="No Duration", duration_seconds=None),
        ]
        options = _build_select_options(entries)

        assert options[0].description is not None  # formatted duration
        assert options[1].description is None

    def test_limited_to_max_select_options(self) -> None:
        from discord_music_player.infrastructure.discord.views.playlist_view import (
            _build_select_options,
        )

        entries = [_make_entry(title=f"Song {i}") for i in range(30)]
        options = _build_select_options(entries)

        assert len(options) == PlaylistConstants.MAX_SELECT_OPTIONS


# =============================================================================
# PlaylistView.__init__ Tests
# =============================================================================


class TestPlaylistViewInit:
    def test_select_added_when_entries_within_limit(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(5)]
        view, _ = _make_view(entries=entries)

        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        assert len(selects) == 1

    def test_select_not_added_when_entries_exceed_limit(self) -> None:
        entries = [
            _make_entry(title=f"Song {i}")
            for i in range(PlaylistConstants.MAX_SELECT_OPTIONS + 1)
        ]
        view, _ = _make_view(entries=entries)

        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        assert len(selects) == 0

    def test_select_added_at_exact_limit(self) -> None:
        entries = [
            _make_entry(title=f"Song {i}") for i in range(PlaylistConstants.MAX_SELECT_OPTIONS)
        ]
        view, _ = _make_view(entries=entries)

        selects = [item for item in view.children if isinstance(item, discord.ui.Select)]
        assert len(selects) == 1

    def test_timeout_matches_constant(self) -> None:
        view, _ = _make_view()
        assert view.timeout == PlaylistConstants.VIEW_TIMEOUT

    def test_entries_truncated_to_max(self) -> None:
        entries = [
            _make_entry(title=f"Song {i}")
            for i in range(PlaylistConstants.MAX_PLAYLIST_TRACKS + 10)
        ]
        view, _ = _make_view(entries=entries)
        assert len(view._entries) == PlaylistConstants.MAX_PLAYLIST_TRACKS


# =============================================================================
# interaction_check Tests
# =============================================================================


class TestInteractionCheck:
    @pytest.mark.asyncio
    async def test_allows_requester(self) -> None:
        view, _ = _make_view(user_id=42)
        interaction = _make_interaction(user_id=42)

        result = await view.interaction_check(interaction)

        assert result is True

    @pytest.mark.asyncio
    async def test_blocks_other_user(self) -> None:
        view, _ = _make_view(user_id=42)
        interaction = _make_interaction(user_id=99)

        result = await view.interaction_check(interaction)

        assert result is False
        interaction.response.send_message.assert_awaited_once()
        call_kwargs = interaction.response.send_message.call_args
        assert call_kwargs[1]["ephemeral"] is True


# =============================================================================
# Button Tests
# =============================================================================


class TestAddAllButton:
    @pytest.mark.asyncio
    async def test_enqueues_all_tracks(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(3)]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        await view.add_all_button.callback(interaction)

        assert container.audio_resolver.resolve.await_count == 3
        assert container.queue_service.enqueue.await_count == 3

    @pytest.mark.asyncio
    async def test_edits_message_with_summary(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(2)]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        await view.add_all_button.callback(interaction)

        interaction.edit_original_response.assert_awaited_once()
        summary = interaction.edit_original_response.call_args[1]["content"]
        assert "2" in summary


class TestShuffleAllButton:
    @pytest.mark.asyncio
    async def test_enqueues_all_tracks_shuffled(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(5)]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        with patch("random.shuffle"):
            await view.shuffle_all_button.callback(interaction)

        assert container.audio_resolver.resolve.await_count == 5


class TestCancelButton:
    @pytest.mark.asyncio
    async def test_cancels_and_edits_message(self) -> None:
        view, _ = _make_view()
        interaction = _make_interaction()

        await view.cancel_button.callback(interaction)

        interaction.response.edit_message.assert_awaited_once()
        call_kwargs = interaction.response.edit_message.call_args[1]
        assert call_kwargs["content"] == "Playlist import cancelled."
        assert call_kwargs["embed"] is None

    @pytest.mark.asyncio
    async def test_disables_all_items(self) -> None:
        view, _ = _make_view()
        interaction = _make_interaction()

        await view.cancel_button.callback(interaction)

        for item in view.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                assert item.disabled is True


# =============================================================================
# _on_select Tests
# =============================================================================


class TestOnSelect:
    @pytest.mark.asyncio
    async def test_enqueues_selected_tracks(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(3)]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        # Patch the select's values property to simulate user selection
        for item in view.children:
            if isinstance(item, discord.ui.Select):
                with patch.object(type(item), "values", new_callable=lambda: property(lambda self: ["0", "2"])):
                    await view._on_select(interaction)
                break

        assert container.audio_resolver.resolve.await_count == 2


# =============================================================================
# _enqueue_tracks Tests
# =============================================================================


class TestEnqueueTracks:
    @pytest.mark.asyncio
    async def test_calls_resolve_and_enqueue(self) -> None:
        entries = [_make_entry(title=f"Song {i}") for i in range(2)]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        await view._enqueue_tracks(interaction, [0, 1])

        assert container.audio_resolver.resolve.await_count == 2
        assert container.queue_service.enqueue.await_count == 2

    @pytest.mark.asyncio
    async def test_should_start_triggers_voice_and_playback(self) -> None:
        entries = [_make_entry()]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        enqueue_result = MagicMock()
        enqueue_result.success = True
        enqueue_result.should_start = True
        container.queue_service.enqueue = AsyncMock(return_value=enqueue_result)
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        await view._enqueue_tracks(interaction, [0])

        container.playback_service.start_playback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_unresolvable_tracks(self) -> None:
        entries = [_make_entry(title="Good"), _make_entry(title="Bad")]
        container = _make_container()
        good_track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(side_effect=[good_track, None])
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()

        await view._enqueue_tracks(interaction, [0, 1])

        # Only 1 enqueue call since second resolve returned None
        assert container.queue_service.enqueue.await_count == 1

    @pytest.mark.asyncio
    async def test_no_guild_returns_early(self) -> None:
        entries = [_make_entry()]
        container = _make_container()
        view, _ = _make_view(entries=entries, container=container)
        interaction = _make_interaction()
        interaction.guild = None

        await view._enqueue_tracks(interaction, [0])

        container.audio_resolver.resolve.assert_not_awaited()


# =============================================================================
# on_timeout Tests
# =============================================================================


class TestOnTimeout:
    @pytest.mark.asyncio
    async def test_disables_items_and_deletes_message(self) -> None:
        view, _ = _make_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        for item in view.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                assert item.disabled is True
        message.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_message_does_not_raise(self) -> None:
        view, _ = _make_view()
        # No message set
        await view.on_timeout()  # should not raise


# =============================================================================
# Race Guard Tests
# =============================================================================


class TestRaceGuard:
    @pytest.mark.asyncio
    async def test_second_button_press_returns_early(self) -> None:
        entries = [_make_entry()]
        container = _make_container()
        track = MagicMock()
        container.audio_resolver.resolve = AsyncMock(return_value=track)
        view, _ = _make_view(entries=entries, container=container)
        interaction1 = _make_interaction()
        interaction2 = _make_interaction()

        # First press succeeds
        await view.add_all_button.callback(interaction1)
        # Second press should hit race guard
        await view.add_all_button.callback(interaction2)

        # Second interaction gets ephemeral message
        interaction2.response.send_message.assert_awaited_once()
        assert interaction2.response.send_message.call_args[1]["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_cancel_then_add_all_returns_early(self) -> None:
        view, _ = _make_view()
        interaction1 = _make_interaction()
        interaction2 = _make_interaction()

        await view.cancel_button.callback(interaction1)
        await view.add_all_button.callback(interaction2)

        # Second interaction gets ephemeral message
        interaction2.response.send_message.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_timeout_then_cancel_returns_early(self) -> None:
        view, _ = _make_view()
        message = AsyncMock()
        view.set_message(message)

        await view.on_timeout()

        interaction = _make_interaction()
        await view.cancel_button.callback(interaction)

        # cancel_button checks _finish_view which returns False
        # so it returns early without editing
        interaction.response.edit_message.assert_not_awaited()
