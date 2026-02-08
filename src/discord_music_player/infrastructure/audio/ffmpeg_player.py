"""FFmpeg-based audio playback with volume control and reconnection."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import discord

from discord_music_player.config.settings import AudioSettings
from discord_music_player.domain.shared.messages import LogTemplates

if TYPE_CHECKING:
    from ...domain.music.entities import Track

logger = logging.getLogger(__name__)


class PlayerState(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class FFmpegConfig:
    reconnect: bool = True
    reconnect_streamed: bool = True
    reconnect_delay_max: int = 5
    disable_video: bool = True
    fade_in_seconds: float = 0.5
    default_volume: float = 0.5
    buffer_size: int = 1024 * 1024

    def get_before_options(self) -> str:
        opts = []
        if self.reconnect:
            opts.append("-reconnect 1")
        if self.reconnect_streamed:
            opts.append("-reconnect_streamed 1")
        if self.reconnect_delay_max:
            opts.append(f"-reconnect_delay_max {self.reconnect_delay_max}")
        return " ".join(opts)

    def get_options(self) -> str:
        opts = []
        if self.disable_video:
            opts.append("-vn")
        if self.fade_in_seconds > 0:
            opts.append(f'-af "afade=t=in:ss=0:d={self.fade_in_seconds}"')
        return " ".join(opts)


class FFmpegPlayer:
    def __init__(
        self, settings: AudioSettings | None = None, config: FFmpegConfig | None = None
    ) -> None:
        self._settings = settings or AudioSettings()
        self._config = config or FFmpegConfig(default_volume=self._settings.default_volume)
        self._active_sources: dict[int, discord.AudioSource] = {}
        self._active_processes: dict[int, subprocess.Popen[bytes]] = {}
        self._states: dict[int, PlayerState] = {}
        self._on_error: Callable[[int, Exception], None] | None = None

    def create_source(
        self, track: Track, volume: float | None = None
    ) -> discord.PCMVolumeTransformer:
        if not track.stream_url:
            raise ValueError(f"Track '{track.title}' has no stream URL")

        before_options = self._config.get_before_options()
        options = self._config.get_options()

        # YouTube-specific headers to avoid 403 errors (Android client User-Agent)
        youtube_headers = (
            '-user_agent "com.google.android.youtube/19.02.39 (Linux; U; Android 14)" '
            '-referer "https://www.youtube.com/" '
            '-headers "Accept-Language: en-US,en;q=0.9"'
        )
        before_options_with_headers = f"{before_options} {youtube_headers}"

        source = discord.FFmpegPCMAudio(
            track.stream_url,
            before_options=before_options_with_headers,
            options=options,
        )

        vol = volume if volume is not None else self._config.default_volume
        volume_source = discord.PCMVolumeTransformer(source, volume=vol)

        return volume_source

    async def play(
        self,
        voice_client: discord.VoiceClient,
        track: Track,
        guild_id: int,
        volume: float | None = None,
        after: Callable[[Exception | None], Any] | None = None,
    ) -> bool:
        self._states[guild_id] = PlayerState.LOADING

        try:
            if voice_client.is_playing():
                voice_client.stop()
                await asyncio.sleep(0.1)

            self._cleanup_guild(guild_id)
            source = self.create_source(track, volume)
            self._active_sources[guild_id] = source

            def cleanup_callback(error: Exception | None) -> None:
                self._cleanup_guild(guild_id)
                self._states[guild_id] = PlayerState.IDLE

                if error:
                    logger.warning(LogTemplates.PLAYBACK_ERROR, guild_id, error)
                    if self._on_error:
                        self._on_error(guild_id, error)

                if after:
                    after(error)

            voice_client.play(source, after=cleanup_callback)
            self._states[guild_id] = PlayerState.PLAYING

            logger.info(LogTemplates.PLAYBACK_STARTED, track.title, guild_id)
            return True

        except discord.ClientException as e:
            logger.error(LogTemplates.FFMPEG_DISCORD_CLIENT_ERROR, e)
            self._states[guild_id] = PlayerState.ERROR
            self._cleanup_guild(guild_id)
            return False
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_START, e)
            self._states[guild_id] = PlayerState.ERROR
            self._cleanup_guild(guild_id)
            return False

    def stop(self, voice_client: discord.VoiceClient, guild_id: int) -> bool:
        self._states[guild_id] = PlayerState.STOPPING

        try:
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()

            self._cleanup_guild(guild_id)
            self._states[guild_id] = PlayerState.IDLE

            logger.info(LogTemplates.PLAYBACK_STOPPED, guild_id)
            return True
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_STOP, e)
            return False

    def pause(self, voice_client: discord.VoiceClient, guild_id: int) -> bool:
        try:
            if voice_client.is_playing():
                voice_client.pause()
                self._states[guild_id] = PlayerState.PAUSED
                logger.debug(LogTemplates.PLAYBACK_PAUSED, guild_id)
                return True
            return False
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_PAUSE, e)
            return False

    def resume(self, voice_client: discord.VoiceClient, guild_id: int) -> bool:
        try:
            if voice_client.is_paused():
                voice_client.resume()
                self._states[guild_id] = PlayerState.PLAYING
                logger.debug(LogTemplates.PLAYBACK_RESUMED, guild_id)
                return True
            return False
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_RESUME, e)
            return False

    def set_volume(self, voice_client: discord.VoiceClient, volume: float) -> bool:
        try:
            source = voice_client.source
            if isinstance(source, discord.PCMVolumeTransformer):
                source.volume = max(0.0, min(2.0, volume))
                return True
            return False
        except Exception as e:
            logger.error(LogTemplates.PLAYBACK_FAILED_VOLUME, e)
            return False

    def get_volume(self, voice_client: discord.VoiceClient) -> float | None:
        try:
            source = voice_client.source
            if isinstance(source, discord.PCMVolumeTransformer):
                return source.volume
            return None
        except Exception:
            return None

    def get_state(self, guild_id: int) -> PlayerState:
        return self._states.get(guild_id, PlayerState.IDLE)

    def _cleanup_guild(self, guild_id: int) -> None:
        source = self._active_sources.pop(guild_id, None)
        if source:
            try:
                source.cleanup()
            except Exception as e:
                logger.debug(LogTemplates.FFMPEG_SOURCE_CLEANUP_ERROR, e)

        process = self._active_processes.pop(guild_id, None)
        if process:
            try:
                process.kill()
                process.wait(timeout=1.0)
            except Exception as e:
                logger.debug(LogTemplates.FFMPEG_PROCESS_CLEANUP_ERROR, e)

    def cleanup_all(self) -> int:
        guild_ids = list(self._active_sources.keys())
        for guild_id in guild_ids:
            self._cleanup_guild(guild_id)

        self._states.clear()
        logger.info(LogTemplates.FFMPEG_RESOURCES_CLEANED, len(guild_ids))
        return len(guild_ids)

    def set_error_handler(self, handler: Callable[[int, Exception], None]) -> None:
        self._on_error = handler

    def get_active_count(self) -> int:
        return len(self._active_sources)
