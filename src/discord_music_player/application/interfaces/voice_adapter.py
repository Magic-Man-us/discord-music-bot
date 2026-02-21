"""Port interface for Discord voice operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from discord_music_player.domain.shared.types import ChannelIdField, DiscordSnowflake

if TYPE_CHECKING:
    from ...domain.music.entities import Track
    from ...domain.music.value_objects import StartSeconds


class VoiceAdapter(ABC):
    """Interface for Discord voice channel operations."""

    @abstractmethod
    async def connect(self, guild_id: DiscordSnowflake, channel_id: ChannelIdField) -> bool:
        """Connect to a voice channel."""
        ...

    @abstractmethod
    async def disconnect(self, guild_id: DiscordSnowflake) -> bool:
        """Disconnect from voice in a guild."""
        ...

    @abstractmethod
    async def ensure_connected(self, guild_id: DiscordSnowflake, channel_id: ChannelIdField) -> bool:
        """Ensure bot is connected to the specified channel, connecting or moving as needed."""
        ...

    @abstractmethod
    async def move_to(self, guild_id: DiscordSnowflake, channel_id: ChannelIdField) -> bool:
        """Move to a different voice channel."""
        ...

    @abstractmethod
    async def play(
        self,
        guild_id: DiscordSnowflake,
        track: "Track",
        *,
        start_seconds: "StartSeconds | None" = None,
    ) -> bool:
        """Start playing a track, optionally seeking to *start_seconds*."""
        ...

    @abstractmethod
    async def stop(self, guild_id: DiscordSnowflake) -> bool:
        """Stop current playback."""
        ...

    @abstractmethod
    async def pause(self, guild_id: DiscordSnowflake) -> bool:
        """Pause current playback."""
        ...

    @abstractmethod
    async def resume(self, guild_id: DiscordSnowflake) -> bool:
        """Resume paused playback."""
        ...

    @abstractmethod
    def is_connected(self, guild_id: DiscordSnowflake) -> bool:
        ...

    @abstractmethod
    def is_playing(self, guild_id: DiscordSnowflake) -> bool:
        ...

    @abstractmethod
    def is_paused(self, guild_id: DiscordSnowflake) -> bool:
        ...

    @abstractmethod
    async def get_listeners(self, guild_id: DiscordSnowflake) -> list[DiscordSnowflake]:
        """Get listener user IDs in the voice channel, excluding the bot."""
        ...

    @abstractmethod
    def get_current_channel_id(self, guild_id: DiscordSnowflake) -> ChannelIdField | None:
        """Get the current voice channel ID, or None if not connected."""
        ...

    @abstractmethod
    def set_on_track_end_callback(
        self,
        callback: Callable[[DiscordSnowflake], Awaitable[None]],
    ) -> None:
        """Set callback for when a track ends."""
        ...
