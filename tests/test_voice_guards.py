"""Tests for voice_guards: every public guard, every rejection branch."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from discord_music_player.infrastructure.discord.guards.voice_guards import (
    can_force_skip,
    check_user_in_voice,
    ensure_dj_role,
    ensure_user_in_voice_and_warm,
    ensure_voice,
    ensure_voice_warmup,
    get_member,
    has_dj_role,
    is_solo_in_channel,
    send_ephemeral,
)

from conftest import (  # noqa: E402  -- pytest adds tests/ to sys.path
    FakeVoiceAdapter,
    FakeVoiceWarmupTracker,
    make_interaction,
    make_member,
    make_role,
    make_user_only,
    make_voice_channel,
    make_voice_state,
)


# =============================================================================
# send_ephemeral
# =============================================================================


@pytest.mark.asyncio
async def test_send_ephemeral_uses_response_when_fresh():
    interaction = make_interaction(response_done=False)
    await send_ephemeral(interaction, "hello")
    interaction.response.send_message.assert_awaited_once_with("hello", ephemeral=True)
    interaction.followup.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_ephemeral_uses_followup_when_already_responded():
    interaction = make_interaction(response_done=True)
    await send_ephemeral(interaction, "world")
    interaction.followup.send.assert_awaited_once_with("world", ephemeral=True)
    interaction.response.send_message.assert_not_awaited()


# =============================================================================
# get_member
# =============================================================================


@pytest.mark.asyncio
async def test_get_member_rejects_when_no_guild():
    interaction = make_interaction(has_guild=False)
    result = await get_member(interaction)
    assert result is None
    interaction.response.send_message.assert_awaited_once()
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == "This command can only be used in a server."


@pytest.mark.asyncio
async def test_get_member_rejects_when_user_is_not_member():
    interaction = make_interaction(user=make_user_only())
    result = await get_member(interaction)
    assert result is None
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == "Could not verify your voice state."


@pytest.mark.asyncio
async def test_get_member_returns_member_when_valid():
    member = make_member(member_id=42)
    interaction = make_interaction(user=member)
    result = await get_member(interaction)
    assert result is member


# =============================================================================
# is_solo_in_channel
# =============================================================================


def test_is_solo_returns_false_when_no_voice():
    member = make_member(voice=None)
    assert is_solo_in_channel(member) is False


def test_is_solo_returns_false_when_no_channel():
    member = make_member(voice=make_voice_state(channel=None))
    assert is_solo_in_channel(member) is False


def test_is_solo_returns_true_when_only_non_bot():
    user = make_member(member_id=1)
    bot = make_member(member_id=2, is_bot=True)
    channel = make_voice_channel(channel_id=10, members=[user, bot])
    user.voice = make_voice_state(channel=channel)
    assert is_solo_in_channel(user) is True


def test_is_solo_returns_false_with_two_non_bot_users():
    a = make_member(member_id=1)
    b = make_member(member_id=2)
    channel = make_voice_channel(channel_id=10, members=[a, b])
    a.voice = make_voice_state(channel=channel)
    assert is_solo_in_channel(a) is False


def test_is_solo_returns_true_when_only_bots():
    bot = make_member(member_id=1, is_bot=True)
    channel = make_voice_channel(channel_id=10, members=[bot])
    bot.voice = make_voice_state(channel=channel)
    assert is_solo_in_channel(bot) is True


# =============================================================================
# ensure_voice_warmup
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_voice_warmup_returns_false_when_no_guild():
    interaction = make_interaction(has_guild=False)
    member = make_member()
    tracker = FakeVoiceWarmupTracker(remaining=10)
    result = await ensure_voice_warmup(interaction, member, tracker)
    assert result is False


@pytest.mark.asyncio
async def test_ensure_voice_warmup_solo_bypasses_warmup():
    user = make_member(member_id=1)
    channel = make_voice_channel(channel_id=10, members=[user])
    user.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=user)
    tracker = FakeVoiceWarmupTracker(remaining=999)  # would normally block
    result = await ensure_voice_warmup(interaction, user, tracker)
    assert result is True


@pytest.mark.asyncio
async def test_ensure_voice_warmup_rejects_when_remaining():
    a = make_member(member_id=1)
    b = make_member(member_id=2)
    channel = make_voice_channel(channel_id=10, members=[a, b])
    a.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=a)
    tracker = FakeVoiceWarmupTracker(remaining=15)
    result = await ensure_voice_warmup(interaction, a, tracker)
    assert result is False
    msg = interaction.response.send_message.call_args[0][0]
    assert "15s" in msg


@pytest.mark.asyncio
async def test_ensure_voice_warmup_passes_when_elapsed():
    a = make_member(member_id=1)
    b = make_member(member_id=2)
    channel = make_voice_channel(channel_id=10, members=[a, b])
    a.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=a)
    tracker = FakeVoiceWarmupTracker(remaining=0)
    assert await ensure_voice_warmup(interaction, a, tracker) is True


# =============================================================================
# ensure_user_in_voice_and_warm
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_user_in_voice_and_warm_member_missing():
    interaction = make_interaction(has_guild=False)
    tracker = FakeVoiceWarmupTracker()
    assert await ensure_user_in_voice_and_warm(interaction, tracker) is False


@pytest.mark.asyncio
async def test_ensure_user_in_voice_and_warm_no_voice():
    interaction = make_interaction(user=make_member(voice=None))
    tracker = FakeVoiceWarmupTracker()
    assert await ensure_user_in_voice_and_warm(interaction, tracker) is False
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_user_in_voice_and_warm_warmup_blocks():
    a = make_member(member_id=1)
    b = make_member(member_id=2)
    channel = make_voice_channel(channel_id=10, members=[a, b])
    a.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=a)
    tracker = FakeVoiceWarmupTracker(remaining=20)
    assert await ensure_user_in_voice_and_warm(interaction, tracker) is False


@pytest.mark.asyncio
async def test_ensure_user_in_voice_and_warm_passes():
    user = make_member(member_id=1)
    channel = make_voice_channel(channel_id=10, members=[user])
    user.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=user)
    tracker = FakeVoiceWarmupTracker(remaining=0)
    assert await ensure_user_in_voice_and_warm(interaction, tracker) is True


# =============================================================================
# ensure_voice
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_voice_member_missing():
    interaction = make_interaction(has_guild=False)
    assert await ensure_voice(interaction, FakeVoiceWarmupTracker(), FakeVoiceAdapter()) is False


@pytest.mark.asyncio
async def test_ensure_voice_no_voice_channel():
    interaction = make_interaction(user=make_member(voice=None))
    result = await ensure_voice(interaction, FakeVoiceWarmupTracker(), FakeVoiceAdapter())
    assert result is False
    interaction.response.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_voice_warmup_blocks():
    a = make_member(member_id=1)
    b = make_member(member_id=2)
    channel = make_voice_channel(channel_id=10, members=[a, b])
    a.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=a)
    tracker = FakeVoiceWarmupTracker(remaining=30)
    assert await ensure_voice(interaction, tracker, FakeVoiceAdapter()) is False


@pytest.mark.asyncio
async def test_ensure_voice_already_connected_does_not_reconnect():
    user = make_member(member_id=1)
    channel = make_voice_channel(channel_id=10, members=[user])
    user.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=user)
    adapter = FakeVoiceAdapter(connected=True)
    assert await ensure_voice(interaction, FakeVoiceWarmupTracker(), adapter) is True
    assert adapter.ensure_connected_calls == []


@pytest.mark.asyncio
async def test_ensure_voice_connects_when_not_yet_connected():
    user = make_member(member_id=1)
    channel = make_voice_channel(channel_id=10, members=[user])
    user.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=user, guild_id=99)
    adapter = FakeVoiceAdapter(connected=False, connect_succeeds=True)
    assert await ensure_voice(interaction, FakeVoiceWarmupTracker(), adapter) is True
    assert adapter.ensure_connected_calls == [(99, 10)]


@pytest.mark.asyncio
async def test_ensure_voice_rejects_when_connect_fails():
    user = make_member(member_id=1)
    channel = make_voice_channel(channel_id=10, members=[user])
    user.voice = make_voice_state(channel=channel)
    interaction = make_interaction(user=user)
    adapter = FakeVoiceAdapter(connected=False, connect_succeeds=False)
    result = await ensure_voice(interaction, FakeVoiceWarmupTracker(), adapter)
    assert result is False
    msg = interaction.response.send_message.call_args[0][0]
    assert "couldn't join" in msg.lower()


# =============================================================================
# check_user_in_voice (existing tests retained, rewritten to use conftest factories)
# =============================================================================


@pytest.mark.asyncio
async def test_check_user_in_voice_rejects_non_member():
    interaction = make_interaction(user=make_user_only())
    assert await check_user_in_voice(interaction, guild_id=1) is False
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == "Could not verify your voice state."


@pytest.mark.asyncio
async def test_check_user_in_voice_rejects_user_not_in_voice():
    interaction = make_interaction(user=make_member(voice=None))
    assert await check_user_in_voice(interaction, guild_id=1) is False


@pytest.mark.asyncio
async def test_check_user_in_voice_rejects_different_channel():
    user = make_member(member_id=1)
    user.voice = make_voice_state(channel=make_voice_channel(channel_id=100))
    interaction = make_interaction(user=user, bot_voice_channel_id=200)
    assert await check_user_in_voice(interaction, guild_id=1) is False
    msg = interaction.response.send_message.call_args[0][0]
    assert msg == "You must be in a voice channel to use this command!"


@pytest.mark.asyncio
async def test_check_user_in_voice_passes_same_channel():
    user = make_member(member_id=1)
    user.voice = make_voice_state(channel=make_voice_channel(channel_id=100))
    interaction = make_interaction(user=user, bot_voice_channel_id=100)
    assert await check_user_in_voice(interaction, guild_id=1) is True


@pytest.mark.asyncio
async def test_check_user_in_voice_passes_when_bot_not_connected():
    user = make_member(member_id=1)
    user.voice = make_voice_state(channel=make_voice_channel(channel_id=100))
    interaction = make_interaction(user=user, bot_voice_channel_id=None)
    assert await check_user_in_voice(interaction, guild_id=1) is True


# =============================================================================
# can_force_skip
# =============================================================================


def test_can_force_skip_admin_passes():
    member = make_member(administrator=True)
    assert can_force_skip(member, owner_ids=()) is True


def test_can_force_skip_owner_passes():
    member = make_member(member_id=42, administrator=False)
    assert can_force_skip(member, owner_ids=(42,)) is True


def test_can_force_skip_rejects_neither():
    member = make_member(member_id=99, administrator=False)
    assert can_force_skip(member, owner_ids=(1, 2, 3)) is False


# =============================================================================
# has_dj_role
# =============================================================================


def test_has_dj_role_unconfigured_allows_everyone():
    member = make_member(roles=[])
    assert has_dj_role(member, dj_role_id=None) is True


def test_has_dj_role_admin_bypasses():
    member = make_member(administrator=True, roles=[])
    assert has_dj_role(member, dj_role_id=500) is True


def test_has_dj_role_passes_when_role_present():
    member = make_member(roles=[make_role(500), make_role(600)])
    assert has_dj_role(member, dj_role_id=500) is True


def test_has_dj_role_rejects_when_role_absent():
    member = make_member(roles=[make_role(600), make_role(700)])
    assert has_dj_role(member, dj_role_id=500) is False


# =============================================================================
# ensure_dj_role
# =============================================================================


@pytest.mark.asyncio
async def test_ensure_dj_role_unconfigured_passes_without_member_fetch():
    interaction = make_interaction(has_guild=False)
    assert await ensure_dj_role(interaction, dj_role_id=None) is True
    interaction.response.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_dj_role_member_missing_rejects():
    interaction = make_interaction(has_guild=False)
    assert await ensure_dj_role(interaction, dj_role_id=500) is False


@pytest.mark.asyncio
async def test_ensure_dj_role_passes_when_member_has_role():
    member = make_member(roles=[make_role(500)])
    interaction = make_interaction(user=member)
    assert await ensure_dj_role(interaction, dj_role_id=500) is True


@pytest.mark.asyncio
async def test_ensure_dj_role_rejects_when_member_lacks_role():
    member = make_member(roles=[make_role(999)])
    interaction = make_interaction(user=member)
    assert await ensure_dj_role(interaction, dj_role_id=500) is False
    msg = interaction.response.send_message.call_args[0][0]
    assert "DJ" in msg


# =============================================================================
# Cog setup() smoke tests — registering without container should raise.
# =============================================================================


@pytest.mark.asyncio
async def test_skip_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.skip_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_queue_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.queue_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_radio_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.radio_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)


@pytest.mark.asyncio
async def test_now_playing_cog_setup_no_container():
    from discord_music_player.infrastructure.discord.cogs.now_playing_cog import setup

    bot = MagicMock()
    del bot.container

    with pytest.raises(RuntimeError):
        await setup(bot)
