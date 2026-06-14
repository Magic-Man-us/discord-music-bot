"""Tests for GuildLockRegistry — per-guild asyncio.Lock with bounded eviction."""

from __future__ import annotations

import pytest

from discord_music_player.infrastructure.discord.services.guild_lock_registry import (
    _MAX_GUILD_LOCKS,
    GuildLockRegistry,
)


def test_same_guild_returns_same_lock():
    reg = GuildLockRegistry()
    assert reg.get(1) is reg.get(1)


def test_different_guilds_get_different_locks():
    reg = GuildLockRegistry()
    assert reg.get(1) is not reg.get(2)


def test_clear_drops_all_locks():
    reg = GuildLockRegistry()
    first = reg.get(1)
    reg.clear()
    assert reg.get(1) is not first


@pytest.mark.asyncio
async def test_eviction_drops_idle_locks_but_spares_held_ones():
    reg = GuildLockRegistry()
    held = reg.get(0)
    idle = reg.get(1)

    async with held:  # guild 0's lock is now held
        # Fill to the cap (guilds 0 and 1 already exist).
        for gid in range(2, _MAX_GUILD_LOCKS):
            reg.get(gid)
        # Inserting a new guild at the cap evicts every currently-unlocked lock.
        reg.get(_MAX_GUILD_LOCKS + 1)

        assert reg.get(0) is held  # held lock survived eviction
        assert reg.get(1) is not idle  # idle lock was evicted → fresh instance
