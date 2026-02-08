"""
Voice Adapter Interface

Port interface for Discord voice operations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...domain.music.entities import Track


class VoiceAdapter(ABC):
    """Abstract interface for voice channel operations.

    Implementations handle Discord-specific voice functionality
    including connection, playback, and listener management.
    """

    @abstractmethod
    async def connect(self, guild_id: int, channel_id: int) -> bool:
        """Connect to a voice channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Voice channel ID.

        Returns:
            True if connection was successful.
        """
        ...

    @abstractmethod
    async def disconnect(self, guild_id: int) -> bool:
        """Disconnect from voice in a guild.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if disconnection was successful.
        """
        ...

    @abstractmethod
    async def ensure_connected(self, guild_id: int, channel_id: int) -> bool:
        """Ensure bot is connected to the specified channel.

        Connects if not connected, moves if in different channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Target voice channel ID.

        Returns:
            True if bot is now in the specified channel.
        """
        ...

    @abstractmethod
    async def move_to(self, guild_id: int, channel_id: int) -> bool:
        """Move to a different voice channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Target voice channel ID.

        Returns:
            True if move was successful.
        """
        ...

    @abstractmethod
    async def play(self, guild_id: int, track: "Track") -> bool:
        """Start playing a track.

        Args:
            guild_id: Discord guild ID.
            track: The track to play.

        Returns:
            True if playback started successfully.
        """
        ...

    @abstractmethod
    async def stop(self, guild_id: int) -> bool:
        """Stop current playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was stopped.
        """
        ...

    @abstractmethod
    async def pause(self, guild_id: int) -> bool:
        """Pause current playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was paused.
        """
        ...

    @abstractmethod
    async def resume(self, guild_id: int) -> bool:
        """Resume paused playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was resumed.
        """
        ...

    @abstractmethod
    def is_connected(self, guild_id: int) -> bool:
        """Check if bot is connected to voice in a guild.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if connected to any voice channel.
        """
        ...

    @abstractmethod
    def is_playing(self, guild_id: int) -> bool:
        """Check if currently playing audio.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if audio is currently playing.
        """
        ...

    @abstractmethod
    def is_paused(self, guild_id: int) -> bool:
        """Check if playback is paused.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback is paused.
        """
        ...

    @abstractmethod
    async def get_listeners(self, guild_id: int) -> list[int]:
        """Get list of listener user IDs in the voice channel.

        Excludes the bot itself.

        Args:
            guild_id: Discord guild ID.

        Returns:
            List of user IDs in the voice channel.
        """
        ...

    @abstractmethod
    def get_current_channel_id(self, guild_id: int) -> int | None:
        """Get the ID of the current voice channel.

        Args:
            guild_id: Discord guild ID.

        Returns:
            Channel ID if connected, None otherwise.
        """
        ...

    @abstractmethod
    def set_on_track_end_callback(
        self,
        callback: Any,  # Callable[[int], Awaitable[None]]
    ) -> None:
        """Set callback for when a track ends.

        Args:
            callback: Async function that takes guild_id as parameter.
        """
        ...
