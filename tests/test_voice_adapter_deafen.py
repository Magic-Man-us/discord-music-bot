"""Tests for DiscordVoiceAdapter self-deafen behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_connect_joins_self_deafened(monkeypatch):
    """connect() should call channel.connect(self_deaf=True)."""
    from discord_music_player.infrastructure.discord.adapters import voice_adapter as va

    class FakeVoiceChannel:
        def __init__(self) -> None:
            self.name = "voice"
            self.connect = AsyncMock()

    class FakeStageChannel:
        pass

    monkeypatch.setattr(va.discord, "VoiceChannel", FakeVoiceChannel)
    monkeypatch.setattr(va.discord, "StageChannel", FakeStageChannel)

    channel = FakeVoiceChannel()

    guild = MagicMock()
    guild.id = 123
    guild.name = "guild"
    guild.get_channel.return_value = channel
    guild.change_voice_state = AsyncMock()

    bot = MagicMock()
    bot.get_guild.return_value = guild

    adapter = va.DiscordVoiceAdapter(bot)

    ok = await adapter.connect(guild_id=123, channel_id=456)

    assert ok is True
    channel.connect.assert_awaited_once()
    await_args = channel.connect.await_args
    assert await_args is not None
    assert await_args.kwargs.get("self_deaf") is True


@pytest.mark.asyncio
async def test_move_to_reapplies_self_deaf(monkeypatch):
    """move_to() should re-apply self_deaf via guild.change_voice_state."""
    from discord_music_player.infrastructure.discord.adapters import voice_adapter as va

    class FakeVoiceChannel:
        def __init__(self) -> None:
            self.name = "voice"

    class FakeStageChannel:
        pass

    monkeypatch.setattr(va.discord, "VoiceChannel", FakeVoiceChannel)
    monkeypatch.setattr(va.discord, "StageChannel", FakeStageChannel)

    channel = FakeVoiceChannel()

    guild = MagicMock()
    guild.id = 123
    guild.get_channel.return_value = channel
    guild.change_voice_state = AsyncMock()

    vc = MagicMock()
    vc.channel = MagicMock()
    vc.channel.id = 999
    vc.move_to = AsyncMock()

    bot = MagicMock()
    bot.get_guild.return_value = guild

    adapter = va.DiscordVoiceAdapter(bot)

    # Force adapter to think we're already connected.
    monkeypatch.setattr(adapter, "_get_voice_client", lambda guild_id: vc)

    ok = await adapter.move_to(guild_id=123, channel_id=456)
    assert ok is True
    vc.move_to.assert_awaited_once_with(channel)
    guild.change_voice_state.assert_awaited_once()
    await_args = guild.change_voice_state.await_args
    assert await_args is not None
    assert await_args.kwargs.get("self_deaf") is True
