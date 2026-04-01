"""Tests for MessageStateManager — per-guild Discord message tracking and editing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.music.wrappers import TrackId
from discord_music_player.infrastructure.discord.services.message_state_manager import (
    MessageStateManager,
)
from discord_music_player.infrastructure.discord.services.models import (
    GuildMessageState,
    TrackedMessage,
    TrackKey,
)

# ============================================================================
# Fixtures
# ============================================================================

GUILD_ID = 111111111
CHANNEL_ID = 222222222
MESSAGE_ID_1 = 333333333
MESSAGE_ID_2 = 444444444


@pytest.fixture
def track_a() -> Track:
    return Track(
        id=TrackId(value="track-a"),
        title="Track Alpha",
        webpage_url="https://youtube.com/watch?v=a",
        duration_seconds=200,
        artist="Artist A",
        requested_by_id=100,
        requested_by_name="Alice",
    )


@pytest.fixture
def track_b() -> Track:
    return Track(
        id=TrackId(value="track-b"),
        title="Track Beta",
        webpage_url="https://youtube.com/watch?v=b",
        duration_seconds=180,
        artist="Artist B",
        requested_by_id=200,
        requested_by_name="Bob",
    )


@pytest.fixture
def mock_bot() -> MagicMock:
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=None)
    bot.fetch_channel = AsyncMock(return_value=None)
    return bot


@pytest.fixture
def manager(mock_bot: MagicMock) -> MessageStateManager:
    return MessageStateManager(mock_bot)


# ============================================================================
# State Management — get_state / reset / clear
# ============================================================================


class TestStateManagement:
    def test_get_state_creates_on_first_access(self, manager: MessageStateManager) -> None:
        state = manager.get_state(GUILD_ID)
        assert isinstance(state, GuildMessageState)
        assert state.now_playing is None
        assert len(state.queued) == 0

    def test_get_state_returns_same_instance(self, manager: MessageStateManager) -> None:
        state1 = manager.get_state(GUILD_ID)
        state2 = manager.get_state(GUILD_ID)
        assert state1 is state2

    def test_different_guilds_get_different_state(self, manager: MessageStateManager) -> None:
        state_a = manager.get_state(111)
        state_b = manager.get_state(222)
        assert state_a is not state_b

    @pytest.mark.asyncio
    async def test_reset_removes_guild_state(self, manager: MessageStateManager) -> None:
        manager.get_state(GUILD_ID)
        await manager.reset(GUILD_ID)
        # Next access should create a fresh state
        state = manager.get_state(GUILD_ID)
        assert state.now_playing is None

    @pytest.mark.asyncio
    async def test_reset_nonexistent_guild_is_noop(self, manager: MessageStateManager) -> None:
        await manager.reset(999)  # should not raise

    def test_clear_all_removes_everything(self, manager: MessageStateManager) -> None:
        manager.get_state(111)
        manager.get_state(222)
        manager.clear_all()
        # Both guilds should get fresh state
        assert manager.get_state(111).now_playing is None
        assert manager.get_state(222).now_playing is None


# ============================================================================
# Track Now Playing / Track Queued
# ============================================================================


class TestTrackMutation:
    def test_track_now_playing(self, manager: MessageStateManager, track_a: Track) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID,
            track=track_a,
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
        )

        state = manager.get_state(GUILD_ID)
        assert state.now_playing is not None
        assert state.now_playing.channel_id == CHANNEL_ID
        assert state.now_playing.message_id == MESSAGE_ID_1
        assert state.now_playing.track_key.track_id == "track-a"

    def test_track_now_playing_replaces_previous(
        self, manager: MessageStateManager, track_a: Track, track_b: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        state = manager.get_state(GUILD_ID)
        assert state.now_playing is not None
        assert state.now_playing.track_key.track_id == "track-b"

    def test_track_queued_appends(
        self, manager: MessageStateManager, track_a: Track, track_b: Track
    ) -> None:
        manager.track_queued(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        manager.track_queued(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        state = manager.get_state(GUILD_ID)
        assert len(state.queued) == 2
        assert state.queued[0].track_key.track_id == "track-a"
        assert state.queued[1].track_key.track_id == "track-b"


# ============================================================================
# Message Fetching
# ============================================================================


class TestFetchMessage:
    @pytest.mark.asyncio
    async def test_fetch_via_get_channel(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager._fetch_message(tracked)
        assert result is mock_message

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_fetch_channel(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)

        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(return_value=mock_channel)

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager._fetch_message(tracked)
        assert result is mock_message

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_channel_not_found(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Not found")
        )

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager._fetch_message(tracked)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_not_messageable(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        # Return a channel that isn't Messageable (e.g., CategoryChannel)
        mock_channel = MagicMock(spec=discord.CategoryChannel)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager._fetch_message(tracked)
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_returns_none_when_message_not_found(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(
            side_effect=discord.HTTPException(MagicMock(), "Unknown Message")
        )
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager._fetch_message(tracked)
        assert result is None


# ============================================================================
# Edit Message Methods
# ============================================================================


class TestEditMessage:
    @pytest.mark.asyncio
    async def test_edit_to_one_liner(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        await manager.edit_message_to_one_liner(tracked, content="Done playing.")

        mock_message.edit.assert_awaited_once_with(content="Done playing.", embed=None, view=None)

    @pytest.mark.asyncio
    async def test_edit_to_one_liner_noop_when_fetch_fails(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "err"))

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        # Should not raise
        await manager.edit_message_to_one_liner(tracked, content="Done.")

    @pytest.mark.asyncio
    async def test_edit_to_one_liner_swallows_http_error(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Forbidden"))
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        # Should not raise — error is caught and logged
        await manager.edit_message_to_one_liner(tracked, content="Done.")

    @pytest.mark.asyncio
    async def test_edit_to_embed_returns_message(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        embed = discord.Embed(title="Now Playing")
        result = await manager.edit_message_to_embed(tracked, embed=embed, view=None)

        assert result is mock_message
        mock_message.edit.assert_awaited_once_with(content=None, embed=embed, view=None)

    @pytest.mark.asyncio
    async def test_edit_to_embed_returns_none_on_http_error(
        self, manager: MessageStateManager, mock_bot: MagicMock
    ) -> None:
        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Forbidden"))
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        tracked = TrackedMessage(
            channel_id=CHANNEL_ID,
            message_id=MESSAGE_ID_1,
            track_key=TrackKey(track_id="t1"),
        )
        result = await manager.edit_message_to_embed(tracked, embed=discord.Embed(), view=None)
        assert result is None


# ============================================================================
# Update Next Up
# ============================================================================


class TestUpdateNextUp:
    @pytest.mark.asyncio
    async def test_updates_next_up_field_to_track_title(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        # Set up now-playing state
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        # Create a message with a "Next Up" field in its embed
        embed = discord.Embed(title="Now Playing")
        embed.add_field(name="⏭️ Next Up", value="Nothing", inline=False)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        await manager.update_next_up(GUILD_ID, track_b)

        mock_message.edit.assert_awaited_once()
        # Verify the field value was actually updated to the track title
        updated_embed = mock_message.edit.call_args.kwargs["embed"]
        next_field = [f for f in updated_embed.fields if "Next Up" in (f.name or "")][0]
        assert track_b.title in next_field.value

    @pytest.mark.asyncio
    async def test_noop_when_no_state(self, manager: MessageStateManager) -> None:
        # No state set — should not raise
        await manager.update_next_up(GUILD_ID, None)

    @pytest.mark.asyncio
    async def test_noop_when_no_now_playing(self, manager: MessageStateManager) -> None:
        manager.get_state(GUILD_ID)  # create state but no now_playing
        await manager.update_next_up(GUILD_ID, None)

    @pytest.mark.asyncio
    async def test_noop_when_message_has_no_embeds(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = []
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        # Should not raise or try to edit
        await manager.update_next_up(GUILD_ID, None)

    @pytest.mark.asyncio
    async def test_noop_when_fetch_returns_none(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        mock_bot.get_channel.return_value = None
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "err"))

        await manager.update_next_up(GUILD_ID, None)  # should not raise

    @pytest.mark.asyncio
    async def test_swallows_edit_exception(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        embed = discord.Embed(title="Now Playing")
        embed.add_field(name="⏭️ Next Up", value="Nothing", inline=False)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [embed]
        mock_message.edit = AsyncMock(side_effect=Exception("edit failed"))

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        # Should not raise — exception is caught
        await manager.update_next_up(GUILD_ID, track_b)

    @pytest.mark.asyncio
    async def test_shows_none_text_when_next_track_is_none(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        from discord_music_player.domain.shared.constants import UIConstants

        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        embed = discord.Embed(title="Now Playing")
        embed.add_field(name="⏭️ Next Up", value="Some Track", inline=False)
        mock_message = MagicMock(spec=discord.Message)
        mock_message.embeds = [embed]
        mock_message.edit = AsyncMock()

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

        await manager.update_next_up(GUILD_ID, None)

        mock_message.edit.assert_awaited_once()
        # The embed field should now show the "no next" text
        updated_embed = mock_message.edit.call_args.kwargs["embed"]
        next_field = [f for f in updated_embed.fields if "Next Up" in (f.name or "")][0]
        assert next_field.value == UIConstants.NEXT_UP_NONE


# ============================================================================
# On Track Finished
# ============================================================================


class TestOnTrackFinished:
    @pytest.mark.asyncio
    async def test_sends_finished_message(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()
        mock_bot.get_channel.return_value = mock_channel

        await manager.on_track_finished(GUILD_ID, track_a)

        from discord_music_player.domain.shared.constants import UIConstants

        mock_channel.send.assert_awaited_once()
        call_args = mock_channel.send.call_args
        assert "Track Alpha" in call_args[0][0]
        assert call_args[1].get("delete_after") == UIConstants.FINISHED_DELETE_AFTER

    @pytest.mark.asyncio
    async def test_noop_when_no_state(self, manager: MessageStateManager, track_a: Track) -> None:
        await manager.on_track_finished(GUILD_ID, track_a)  # should not raise

    @pytest.mark.asyncio
    async def test_noop_when_no_now_playing(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.get_state(GUILD_ID)  # no now_playing set
        await manager.on_track_finished(GUILD_ID, track_a)  # should not raise
        mock_bot.get_channel.assert_not_called()  # verify early exit was taken

    @pytest.mark.asyncio
    async def test_swallows_send_http_error(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Forbidden"))
        mock_bot.get_channel.return_value = mock_channel

        # Should not raise
        await manager.on_track_finished(GUILD_ID, track_a)

    @pytest.mark.asyncio
    async def test_noop_when_channel_not_messageable(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track
    ) -> None:
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        # Return a non-messageable channel
        mock_bot.get_channel.return_value = MagicMock(spec=discord.CategoryChannel)

        await manager.on_track_finished(GUILD_ID, track_a)  # should not raise


# ============================================================================
# Promote Next Track
# ============================================================================


class TestPromoteNextTrack:
    def _setup_channel(self, mock_bot: MagicMock, mock_message: MagicMock) -> None:
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_message)
        mock_bot.get_channel.return_value = mock_channel

    @pytest.mark.asyncio
    async def test_reuses_now_playing_message(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When now_playing exists and edit succeeds, reuse it for the next track."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        await manager.promote_next_track(GUILD_ID, track_b)

        mock_message.edit.assert_awaited_once()
        # now_playing should still be the same TrackedMessage (reused, not replaced)
        state = manager.get_state(GUILD_ID)
        assert state.now_playing is not None
        assert state.now_playing.message_id == MESSAGE_ID_1
        # Deliberate: track_key still references the original track, not the promoted one.
        # The TrackedMessage is frozen and reused for its channel/message IDs only.
        assert state.now_playing.track_key.track_id == "track-a"

    @pytest.mark.asyncio
    async def test_falls_back_to_queued_message(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When no now_playing exists, promote a matching queued message."""
        manager.track_queued(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        await manager.promote_next_track(GUILD_ID, track_b)

        mock_message.edit.assert_awaited_once()
        state = manager.get_state(GUILD_ID)
        # The queued message should now be the now_playing
        assert state.now_playing is not None
        assert state.now_playing.message_id == MESSAGE_ID_2
        assert len(state.queued) == 0

    @pytest.mark.asyncio
    async def test_discards_queued_when_reusing_now_playing(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When reusing now_playing, any queued message for the next track is removed."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        manager.track_queued(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        await manager.promote_next_track(GUILD_ID, track_b)

        state = manager.get_state(GUILD_ID)
        assert len(state.queued) == 0

    @pytest.mark.asyncio
    async def test_noop_when_no_state(self, manager: MessageStateManager, track_b: Track) -> None:
        # No state at all — should not raise
        await manager.promote_next_track(GUILD_ID, track_b)

    @pytest.mark.asyncio
    async def test_noop_when_neither_now_playing_nor_queued(
        self, manager: MessageStateManager, track_b: Track
    ) -> None:
        manager.get_state(GUILD_ID)  # empty state
        await manager.promote_next_track(GUILD_ID, track_b)

    @pytest.mark.asyncio
    async def test_now_playing_edit_fails_queued_already_discarded(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When now_playing exists, queued is discarded first; if edit fails, now_playing is unchanged."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )
        manager.track_queued(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        mock_msg_fail = MagicMock(spec=discord.Message)
        mock_msg_fail.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "err"))
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg_fail)
        mock_bot.get_channel.return_value = mock_channel

        await manager.promote_next_track(GUILD_ID, track_b)

        state = manager.get_state(GUILD_ID)
        # now_playing still points to old message (edit failed, queued was already discarded)
        assert state.now_playing is not None
        assert state.now_playing.message_id == MESSAGE_ID_1
        assert len(state.queued) == 0

    @pytest.mark.asyncio
    async def test_promotes_queued_when_no_now_playing_and_edit_fails(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_b: Track
    ) -> None:
        """When no now_playing and queued edit also fails, now_playing stays None."""
        manager.track_queued(
            guild_id=GUILD_ID, track=track_b, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_2
        )

        mock_msg_fail = MagicMock(spec=discord.Message)
        mock_msg_fail.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "err"))
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg_fail)
        mock_bot.get_channel.return_value = mock_channel

        await manager.promote_next_track(GUILD_ID, track_b)

        state = manager.get_state(GUILD_ID)
        assert state.now_playing is None
        assert len(state.queued) == 0

    @pytest.mark.asyncio
    async def test_passes_container_to_create_now_playing_view(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When container is provided, should create NowPlayingView."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        mock_container = MagicMock()

        with patch(
            "discord_music_player.infrastructure.discord.views.now_playing_view.NowPlayingView"
        ) as mock_view_cls:
            mock_view = MagicMock()
            mock_view_cls.return_value = mock_view

            await manager.promote_next_track(GUILD_ID, track_b, container=mock_container)

            mock_view_cls.assert_called_once_with(
                webpage_url=track_b.webpage_url,
                title=track_b.title,
                guild_id=GUILD_ID,
                container=mock_container,
            )
            mock_view.set_message.assert_called_once_with(mock_message)

    @pytest.mark.asyncio
    async def test_uses_download_view_without_container(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """When container is None, should create DownloadView."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        with patch(
            "discord_music_player.infrastructure.discord.views.download_view.DownloadView"
        ) as mock_view_cls:
            mock_view = MagicMock()
            mock_view_cls.return_value = mock_view

            await manager.promote_next_track(GUILD_ID, track_b, container=None)

            mock_view_cls.assert_called_once_with(
                webpage_url=track_b.webpage_url, title=track_b.title
            )

    @pytest.mark.asyncio
    async def test_passes_upcoming_track_to_embed(
        self, manager: MessageStateManager, mock_bot: MagicMock, track_a: Track, track_b: Track
    ) -> None:
        """The upcoming_track kwarg should be forwarded to build_now_playing_embed."""
        manager.track_now_playing(
            guild_id=GUILD_ID, track=track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1
        )

        mock_message = MagicMock(spec=discord.Message)
        mock_message.edit = AsyncMock()
        self._setup_channel(mock_bot, mock_message)

        with patch(
            "discord_music_player.infrastructure.discord.services.message_state_manager.build_now_playing_embed"
        ) as mock_build:
            mock_build.return_value = discord.Embed(title="NP")
            await manager.promote_next_track(GUILD_ID, track_b, upcoming_track=track_a)
            mock_build.assert_called_once_with(track_b, next_track=track_a)


# ============================================================================
# Pydantic Models — TrackKey / TrackedMessage / GuildMessageState
# ============================================================================


class TestModels:
    def test_track_key_from_track(self, track_a: Track) -> None:
        key = TrackKey.from_track(track_a)
        assert key.track_id == "track-a"
        assert key.requested_by_id == 100

    def test_tracked_message_for_track(self, track_a: Track) -> None:
        msg = TrackedMessage.for_track(track_a, channel_id=CHANNEL_ID, message_id=MESSAGE_ID_1)
        assert msg.channel_id == CHANNEL_ID
        assert msg.message_id == MESSAGE_ID_1
        assert msg.track_key.track_id == "track-a"

    def test_pop_matching_queued_finds_and_removes(self, track_a: Track, track_b: Track) -> None:
        state = GuildMessageState()
        msg_a = TrackedMessage.for_track(track_a, channel_id=1, message_id=10)
        msg_b = TrackedMessage.for_track(track_b, channel_id=1, message_id=20)
        state.queued.append(msg_a)
        state.queued.append(msg_b)

        result = state.pop_matching_queued(track_a)
        assert result is not None
        assert result.track_key.track_id == "track-a"
        assert len(state.queued) == 1
        assert state.queued[0].track_key.track_id == "track-b"

    def test_pop_matching_queued_returns_none_when_not_found(
        self, track_a: Track, track_b: Track
    ) -> None:
        state = GuildMessageState()
        msg_b = TrackedMessage.for_track(track_b, channel_id=1, message_id=20)
        state.queued.append(msg_b)

        result = state.pop_matching_queued(track_a)
        assert result is None
        assert len(state.queued) == 1

    def test_pop_matching_queued_empty_deque(self, track_a: Track) -> None:
        state = GuildMessageState()
        result = state.pop_matching_queued(track_a)
        assert result is None
