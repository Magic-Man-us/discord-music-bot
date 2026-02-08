"""
Discord Voice Adapter

Infrastructure implementation of VoiceAdapter for Discord voice operations.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import discord

from discord_music_player.application.interfaces.voice_adapter import VoiceAdapter
from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ....domain.music.entities import Track

logger = logging.getLogger(__name__)

# Connection timeout
CONNECT_TIMEOUT: float = 10.0

# Audio settings
FADE_IN_SECONDS: float = 0.5
DEFAULT_VOLUME: float = 0.2

# User agent to match yt-dlp's Android client (required to avoid 403 from YouTube)
ANDROID_USER_AGENT = "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip"


class DiscordVoiceAdapter(VoiceAdapter):
    """Discord voice client adapter.

    Handles all Discord-specific voice operations including
    connection, disconnection, and audio playback.
    """

    def __init__(self, bot: discord.Client, settings: AudioSettings | None = None) -> None:
        """Initialize the voice adapter.

        Args:
            bot: Discord bot client instance.
            settings: Audio settings for configuration.
        """
        self._bot = bot
        self._settings = settings or AudioSettings()
        self._volume = self._settings.default_volume
        self._on_track_end: Callable[[int], Awaitable[None]] | None = None

        # Track currently playing tracks per guild
        self._current_track: dict[int, Track] = {}

        # FFmpeg options from settings
        self._ffmpeg_options = self._settings.ffmpeg_options

    def _get_voice_client(self, guild_id: int) -> discord.VoiceClient | None:
        """Get the voice client for a guild.

        Args:
            guild_id: Discord guild ID.

        Returns:
            VoiceClient if connected, None otherwise.
        """
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return None

        vc = guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) else None

    def _get_guild(self, guild_id: int) -> discord.Guild | None:
        """Get a guild by ID.

        Args:
            guild_id: Discord guild ID.

        Returns:
            Guild if found, None otherwise.
        """
        return self._bot.get_guild(guild_id)

    async def connect(self, guild_id: int, channel_id: int) -> bool:
        """Connect to a voice channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Voice channel ID.

        Returns:
            True if connection was successful.
        """
        guild = self._get_guild(guild_id)
        if not guild:
            logger.warning(LogTemplates.GUILD_NOT_FOUND, guild_id)
            return False

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            logger.warning(LogTemplates.CHANNEL_NOT_VOICE, channel_id)
            return False

        try:
            # Use asyncio.timeout for cleaner timeout handling (Python 3.11+)
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await channel.connect(self_deaf=True)
            await self._ensure_self_deaf(guild, channel)
            logger.info(
                LogTemplates.VOICE_CONNECTED,
                channel.name,
                guild.name,
            )
            return True
        except TimeoutError:
            logger.error(LogTemplates.VOICE_CONNECTION_TIMEOUT, channel_id)
            return False
        except discord.ClientException as e:
            logger.error(LogTemplates.VOICE_CLIENT_ERROR, e)
            return False
        except discord.Forbidden:
            logger.error(LogTemplates.VOICE_NO_PERMISSION, channel_id)
            return False
        except Exception:
            logger.exception("Failed to connect to voice")
            return False

    async def _ensure_self_deaf(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel | discord.StageChannel | None,
    ) -> None:
        """Ensure the bot is self-deafened in the guild's current voice connection."""
        try:
            if channel is None:
                return
            await guild.change_voice_state(channel=channel, self_deaf=True)
        except Exception as exc:
            logger.debug(LogTemplates.VOICE_SELF_DEAFEN_FAILED, guild.id, exc)

    async def disconnect(self, guild_id: int) -> bool:
        """Disconnect from voice in a guild.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if disconnection was successful.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            return True  # Not connected

        try:
            # Clear current track
            self._current_track.pop(guild_id, None)

            await vc.disconnect(force=True)
            logger.info(LogTemplates.VOICE_DISCONNECTED, guild_id)
            return True
        except Exception:
            logger.exception("Failed to disconnect from voice")
            return False

    async def ensure_connected(self, guild_id: int, channel_id: int) -> bool:
        """Ensure bot is connected to the specified channel.

        Connects if not connected, moves if in different channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Target voice channel ID.

        Returns:
            True if bot is now in the specified channel.
        """
        vc = self._get_voice_client(guild_id)

        # Clean up stale/disconnected voice clients
        if vc and not vc.is_connected():
            logger.warning(LogTemplates.VOICE_STALE_CLEANUP, guild_id)
            await self.disconnect(guild_id)
            vc = None

        if vc and vc.channel:
            if vc.channel.id == channel_id:
                return True  # Already in the right channel
            # Move to new channel
            return await self.move_to(guild_id, channel_id)

        # Not connected, connect
        return await self.connect(guild_id, channel_id)

    async def move_to(self, guild_id: int, channel_id: int) -> bool:
        """Move to a different voice channel.

        Args:
            guild_id: Discord guild ID.
            channel_id: Target voice channel ID.

        Returns:
            True if move was successful.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            return await self.connect(guild_id, channel_id)

        guild = self._get_guild(guild_id)
        if not guild:
            return False

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            logger.warning(LogTemplates.CHANNEL_NOT_VOICE, channel_id)
            return False

        try:
            # Use asyncio.timeout for cleaner timeout handling (Python 3.11+)
            async with asyncio.timeout(CONNECT_TIMEOUT):
                await vc.move_to(channel)
            await self._ensure_self_deaf(guild, channel)
            logger.info(LogTemplates.VOICE_MOVED, channel.name)
            return True
        except TimeoutError:
            logger.error(LogTemplates.VOICE_MOVE_TIMEOUT, channel_id)
            return False
        except Exception:
            logger.exception("Failed to move to channel")
            return False

    async def play(self, guild_id: int, track: Track) -> bool:
        """Start playing a track.

        Args:
            guild_id: Discord guild ID.
            track: The track to play.

        Returns:
            True if playback started successfully.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            logger.warning(LogTemplates.VOICE_NOT_CONNECTED, guild_id)
            return False

        if not track.stream_url:
            logger.error(LogTemplates.YTDLP_NO_STREAM_URL, track.title)
            return False

        # Stop any current playback
        if vc.is_playing():
            vc.stop()

        try:
            # Build FFmpeg audio source with fade-in
            # Include User-Agent header to match yt-dlp's Android client (prevents 403)
            base_before_opts = self._ffmpeg_options.get("before_options", "")
            before_opts = f'{base_before_opts} -headers "User-Agent: {ANDROID_USER_AGENT}"'
            base_opts = self._ffmpeg_options.get("options", "")

            # Add fade-in filter
            fade_opts = f'{base_opts} -af "afade=t=in:ss=0:d={FADE_IN_SECONDS}"'

            source = discord.FFmpegPCMAudio(
                track.stream_url,
                before_options=before_opts,
                options=fade_opts,
            )

            # Wrap in volume transformer
            volume_source = discord.PCMVolumeTransformer(source, volume=self._volume)

            # Store current track
            self._current_track[guild_id] = track

            # Create after callback
            def after_callback(error: Exception | None = None) -> None:
                logger.info(LogTemplates.TRACK_ENDED, guild_id, error)
                if error:
                    logger.warning(LogTemplates.PLAYBACK_ERROR, guild_id, error)

                # Schedule cleanup on event loop (thread-safe)
                asyncio.run_coroutine_threadsafe(
                    self._handle_track_end(guild_id),
                    self._bot.loop,
                )

            vc.play(volume_source, after=after_callback)
            logger.info(LogTemplates.PLAYBACK_STARTED, track.title, guild_id)
            return True

        except discord.ClientException as e:
            logger.error(LogTemplates.VOICE_CLIENT_ERROR, e)
            return False
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_START, e)
            return False

    async def stop(self, guild_id: int) -> bool:
        """Stop current playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was stopped.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            return True

        if vc.is_playing() or vc.is_paused():
            vc.stop()
            self._current_track.pop(guild_id, None)
            logger.info(LogTemplates.PLAYBACK_STOPPED, guild_id)
            return True

        return True

    async def pause(self, guild_id: int) -> bool:
        """Pause current playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was paused.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            return False

        if vc.is_playing():
            vc.pause()
            logger.info(LogTemplates.PLAYBACK_PAUSED, guild_id)
            return True

        return False

    async def resume(self, guild_id: int) -> bool:
        """Resume paused playback.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback was resumed.
        """
        vc = self._get_voice_client(guild_id)
        if not vc:
            return False

        if vc.is_paused():
            vc.resume()
            logger.info(LogTemplates.PLAYBACK_RESUMED, guild_id)
            return True

        return False

    def is_connected(self, guild_id: int) -> bool:
        """Check if bot is connected to voice in a guild.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if connected to any voice channel.
        """
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_connected()

    def is_playing(self, guild_id: int) -> bool:
        """Check if currently playing audio.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if audio is currently playing.
        """
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_playing()

    def is_paused(self, guild_id: int) -> bool:
        """Check if playback is paused.

        Args:
            guild_id: Discord guild ID.

        Returns:
            True if playback is paused.
        """
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_paused()

    async def get_listeners(self, guild_id: int) -> list[int]:
        """Get list of listener user IDs in the voice channel.

        Excludes the bot itself.

        Args:
            guild_id: Discord guild ID.

        Returns:
            List of user IDs in the voice channel.
        """
        vc = self._get_voice_client(guild_id)
        if not vc or not vc.channel:
            return []

        listeners: list[int] = []
        for member in vc.channel.members:
            # Exclude bots
            if member.bot:
                continue
            # Exclude deafened users (they can't hear)
            if member.voice and member.voice.deaf:
                continue
            if member.voice and member.voice.self_deaf:
                continue
            listeners.append(member.id)

        return listeners

    def get_current_channel_id(self, guild_id: int) -> int | None:
        """Get the ID of the current voice channel.

        Args:
            guild_id: Discord guild ID.

        Returns:
            Channel ID if connected, None otherwise.
        """
        vc = self._get_voice_client(guild_id)
        if vc and vc.channel:
            return vc.channel.id
        return None

    def set_on_track_end_callback(
        self,
        callback: Any,  # Callable[[int], Awaitable[None]]
    ) -> None:
        """Set callback for when a track ends.

        Args:
            callback: Async function that takes guild_id as parameter.
        """
        self._on_track_end = callback

    async def _handle_track_end(self, guild_id: int) -> None:
        """Handle track end cleanup (runs on event loop).

        This method is called from the FFmpeg callback thread via
        run_coroutine_threadsafe to ensure thread-safe cleanup.

        Args:
            guild_id: Discord guild ID.
        """
        # Clear current track (now safe - running on event loop)
        self._current_track.pop(guild_id, None)

        # Call track end callback if set
        if self._on_track_end:
            logger.debug(LogTemplates.PLAYBACK_CALLING_CALLBACK, guild_id)
            try:
                await self._on_track_end(guild_id)
            except Exception as e:
                logger.error(LogTemplates.PLAYBACK_CALLBACK_ERROR, guild_id, e)
        else:
            logger.warning(LogTemplates.PLAYBACK_NO_CALLBACK, guild_id)

    def get_current_track(self, guild_id: int) -> Track | None:
        """Get the currently playing track.

        Args:
            guild_id: Discord guild ID.

        Returns:
            Current track if playing, None otherwise.
        """
        return self._current_track.get(guild_id)

    def set_volume(self, guild_id: int, volume: float) -> bool:
        """Set the playback volume.

        Args:
            guild_id: Discord guild ID.
            volume: Volume level (0.0 to 2.0).

        Returns:
            True if volume was set.
        """
        vc = self._get_voice_client(guild_id)
        if not vc or not vc.source:
            return False

        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = max(0.0, min(2.0, volume))
            return True

        return False

    @asynccontextmanager
    async def voice_connection(self, guild_id: int, channel_id: int) -> AsyncIterator[bool]:
        """Async context manager for voice connections with guaranteed cleanup.

        This ensures voice connections are properly cleaned up even if errors occur.

        Args:
            guild_id: Discord guild ID.
            channel_id: Voice channel ID.

        Yields:
            True if connection was established successfully.

        Example:
            >>> async with adapter.voice_connection(guild_id, channel_id) as connected:
            ...     if connected:
            ...         # Connection established, do work
            ...         await adapter.play(guild_id, track)
            ... # Connection automatically cleaned up on exit
        """
        connected = False
        try:
            connected = await self.ensure_connected(guild_id, channel_id)
            yield connected
        except Exception as e:
            logger.exception("Error in voice connection context:", extra={"exception": e})
            raise
        finally:
            # Cleanup: disconnect if we established the connection
            if connected:
                try:
                    await self.disconnect(guild_id)
                    logger.debug(LogTemplates.VOICE_CONNECTION_CLEANED_UP, guild_id)
                except Exception:
                    logger.error(LogTemplates.VOICE_CLEANUP_ERROR)
