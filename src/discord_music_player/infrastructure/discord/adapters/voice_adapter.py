"""Discord voice adapter implementing VoiceAdapter for connection and playback."""

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

CONNECT_TIMEOUT: float = 10.0
FADE_IN_SECONDS: float = 0.5
DEFAULT_VOLUME: float = 0.2

# Matches yt-dlp's Android client user-agent to avoid YouTube 403 responses
ANDROID_USER_AGENT = "com.google.android.youtube/19.44.38 (Linux; U; Android 14) gzip"


class DiscordVoiceAdapter(VoiceAdapter):
    def __init__(self, bot: discord.Client, settings: AudioSettings | None = None) -> None:
        self._bot = bot
        self._settings = settings or AudioSettings()
        self._volume = self._settings.default_volume
        self._on_track_end: Callable[[int], Awaitable[None]] | None = None
        self._current_track: dict[int, Track] = {}
        self._ffmpeg_options = self._settings.ffmpeg_options

    def _get_voice_client(self, guild_id: int) -> discord.VoiceClient | None:
        guild = self._bot.get_guild(guild_id)
        if not guild:
            return None

        vc = guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) else None

    def _get_guild(self, guild_id: int) -> discord.Guild | None:
        return self._bot.get_guild(guild_id)

    # TODO(integ): Test real voice connect with a test bot in a test guild.
    # Verify: successful connect, self-deaf, timeout, permission denied (Forbidden).
    async def connect(self, guild_id: int, channel_id: int) -> bool:
        guild = self._get_guild(guild_id)
        if not guild:
            logger.warning(LogTemplates.GUILD_NOT_FOUND, guild_id)
            return False

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
            logger.warning(LogTemplates.CHANNEL_NOT_VOICE, channel_id)
            return False

        try:
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

    # TODO(integ): Test real disconnect after a live connect. Verify voice_client is cleaned up.
    async def disconnect(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            return True  # Not connected

        try:
            self._current_track.pop(guild_id, None)

            await vc.disconnect(force=True)
            logger.info(LogTemplates.VOICE_DISCONNECTED, guild_id)
            return True
        except Exception:
            logger.exception("Failed to disconnect from voice")
            return False

    # TODO(integ): Test ensure_connected across scenarios: not connected, already in
    # same channel (no-op), in a different channel (should move). Use two voice channels.
    async def ensure_connected(self, guild_id: int, channel_id: int) -> bool:
        """Connect if not connected, move if in a different channel."""
        vc = self._get_voice_client(guild_id)

        if vc and not vc.is_connected():
            logger.warning(LogTemplates.VOICE_STALE_CLEANUP, guild_id)
            await self.disconnect(guild_id)
            vc = None

        if vc and vc.channel:
            if vc.channel.id == channel_id:
                return True
            return await self.move_to(guild_id, channel_id)

        return await self.connect(guild_id, channel_id)

    # TODO(integ): Test moving between two real voice channels in the test guild.
    async def move_to(self, guild_id: int, channel_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            return await self.connect(guild_id, channel_id)

        guild = self._get_guild(guild_id)
        if not guild:
            return False

        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel | discord.StageChannel):
            logger.warning(LogTemplates.CHANNEL_NOT_VOICE, channel_id)
            return False

        try:
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

    # TODO(integ): Test playing a short audio clip via FFmpeg on a live voice connection.
    # Verify: is_playing() returns True, volume transformer is applied, after_callback fires
    # when the clip ends, and _handle_track_end propagates correctly.
    async def play(self, guild_id: int, track: Track) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            logger.warning(LogTemplates.VOICE_NOT_CONNECTED, guild_id)
            return False

        if not track.stream_url:
            logger.error(LogTemplates.YTDLP_NO_STREAM_URL, track.title)
            return False

        if vc.is_playing():
            vc.stop()

        try:
            # User-Agent must match yt-dlp's Android client to prevent YouTube 403
            base_before_opts = self._ffmpeg_options.get("before_options", "")
            before_opts = f'{base_before_opts} -headers "User-Agent: {ANDROID_USER_AGENT}"'
            base_opts = self._ffmpeg_options.get("options", "")

            fade_opts = f'{base_opts} -af "afade=t=in:ss=0:d={FADE_IN_SECONDS}"'

            source = discord.FFmpegPCMAudio(
                track.stream_url,
                before_options=before_opts,
                options=fade_opts,
            )

            volume_source = discord.PCMVolumeTransformer(source, volume=self._volume)
            self._current_track[guild_id] = track

            def after_callback(error: Exception | None = None) -> None:
                logger.info(LogTemplates.TRACK_ENDED, guild_id, error)
                if error:
                    logger.warning(LogTemplates.PLAYBACK_ERROR, guild_id, error)

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

    # TODO(integ): Test stop while audio is playing. Verify is_playing() becomes False.
    async def stop(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            return True

        if vc.is_playing() or vc.is_paused():
            vc.stop()
            self._current_track.pop(guild_id, None)
            logger.info(LogTemplates.PLAYBACK_STOPPED, guild_id)
            return True

        return True

    # TODO(integ): Test pause/resume cycle on a live voice connection.
    # Verify: pause → is_paused() True, resume → is_playing() True.
    async def pause(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            return False

        if vc.is_playing():
            vc.pause()
            logger.info(LogTemplates.PLAYBACK_PAUSED, guild_id)
            return True

        return False

    async def resume(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc:
            return False

        if vc.is_paused():
            vc.resume()
            logger.info(LogTemplates.PLAYBACK_RESUMED, guild_id)
            return True

        return False

    def is_connected(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_connected()

    def is_playing(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_playing()

    def is_paused(self, guild_id: int) -> bool:
        vc = self._get_voice_client(guild_id)
        return vc is not None and vc.is_paused()

    # TODO(integ): Test with real members in a test voice channel. Verify bots and
    # server-deafened members are excluded from the returned list.
    async def get_listeners(self, guild_id: int) -> list[int]:
        """Return user IDs of non-bot, non-deafened members in the voice channel."""
        vc = self._get_voice_client(guild_id)
        if not vc or not vc.channel:
            return []

        listeners: list[int] = []
        for member in vc.channel.members:
            if member.bot:
                continue
            if member.voice and member.voice.deaf:
                continue
            if member.voice and member.voice.self_deaf:
                continue
            listeners.append(member.id)

        return listeners

    def get_current_channel_id(self, guild_id: int) -> int | None:
        vc = self._get_voice_client(guild_id)
        if vc and vc.channel:
            return vc.channel.id
        return None

    def set_on_track_end_callback(
        self,
        callback: Any,  # Callable[[int], Awaitable[None]]
    ) -> None:
        self._on_track_end = callback

    # TODO(integ): Test that the track-end callback fires via run_coroutine_threadsafe
    # after a short clip finishes. This is the hardest piece to unit-test because it
    # bridges FFmpeg's synchronous thread callback into the async event loop.
    async def _handle_track_end(self, guild_id: int) -> None:
        """Called from the FFmpeg thread via run_coroutine_threadsafe for thread-safe cleanup."""
        self._current_track.pop(guild_id, None)

        if self._on_track_end:
            logger.debug(LogTemplates.PLAYBACK_CALLING_CALLBACK, guild_id)
            try:
                await self._on_track_end(guild_id)
            except Exception as e:
                logger.error(LogTemplates.PLAYBACK_CALLBACK_ERROR, guild_id, e)
        else:
            logger.warning(LogTemplates.PLAYBACK_NO_CALLBACK, guild_id)

    def get_current_track(self, guild_id: int) -> Track | None:
        return self._current_track.get(guild_id)

    # TODO(integ): Test volume adjustment during live playback. Verify PCMVolumeTransformer
    # source is updated and clamped to [0.0, 2.0].
    def set_volume(self, guild_id: int, volume: float) -> bool:
        vc = self._get_voice_client(guild_id)
        if not vc or not vc.source:
            return False

        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = max(0.0, min(2.0, volume))
            return True

        return False

    # TODO(integ): Test the context manager lifecycle: connects on enter, disconnects on
    # exit (including on exception). Verify no leaked voice connections.
    @asynccontextmanager
    async def voice_connection(self, guild_id: int, channel_id: int) -> AsyncIterator[bool]:
        """Context manager that connects on enter and disconnects on exit."""
        connected = False
        try:
            connected = await self.ensure_connected(guild_id, channel_id)
            yield connected
        except Exception as e:
            logger.exception("Error in voice connection context:", extra={"exception": e})
            raise
        finally:
            if connected:
                try:
                    await self.disconnect(guild_id)
                    logger.debug(LogTemplates.VOICE_CONNECTION_CLEANED_UP, guild_id)
                except Exception:
                    logger.error(LogTemplates.VOICE_CLEANUP_ERROR)
