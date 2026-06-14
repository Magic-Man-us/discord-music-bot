"""Per-guild ``asyncio.Lock`` registry with bounded, idle-only eviction."""

from __future__ import annotations

import asyncio

from ....domain.shared.types import DiscordSnowflake

_MAX_GUILD_LOCKS = 256


class GuildLockRegistry:
    """Hands out one ``asyncio.Lock`` per guild, bounding memory by eviction.

    When the registry reaches its cap, every currently-unlocked guild's lock is
    dropped before a new one is created, so locks that are actively held are
    never disturbed.
    """

    def __init__(self) -> None:
        self._locks: dict[DiscordSnowflake, asyncio.Lock] = {}

    def get(self, guild_id: DiscordSnowflake) -> asyncio.Lock:
        lock = self._locks.get(guild_id)
        if lock is None:
            if len(self._locks) >= _MAX_GUILD_LOCKS:
                for gid in [g for g, held in self._locks.items() if not held.locked()]:
                    del self._locks[gid]
            lock = asyncio.Lock()
            self._locks[guild_id] = lock
        return lock

    def clear(self) -> None:
        self._locks.clear()
