"""Playback Application Service - orchestrates audio playback operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...domain.music.entities import GuildPlaybackSession, Track
from ...domain.music.value_objects import PlaybackState
from ...domain.shared.events import QueueExhausted, get_event_bus
from ...domain.shared.messages import ErrorMessages, LogTemplates
from ...domain.shared.types import DiscordSnowflake

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository, TrackHistoryRepository
    from ...domain.music.services import PlaybackDomainService
    from ...domain.music.value_objects import StartSeconds
    from ..interfaces.audio_resolver import AudioResolver
    from ..interfaces.voice_adapter import VoiceAdapter

logger = logging.getLogger(__name__)


class PlaybackApplicationService:
    """Orchestrates audio playback across domain, voice adapter, and audio resolver."""

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        history_repository: TrackHistoryRepository,
        voice_adapter: VoiceAdapter,
        audio_resolver: AudioResolver,
        playback_domain_service: PlaybackDomainService,
    ) -> None:
        self._session_repo = session_repository
        self._history_repo = history_repository
        self._voice_adapter = voice_adapter
        self._audio_resolver = audio_resolver
        self._playback_service = playback_domain_service

        self._on_track_finished_callback: Callable[[DiscordSnowflake, Track], Any] | None = None

        # Optional seek offset consumed on next playback start per guild.
        self._pending_start_seconds: dict[DiscordSnowflake, StartSeconds] = {}

        # When we intentionally stop audio (skip/stop), discord.py still fires
        # the "after" callback. Suppress the next event per guild to avoid double-advancing.
        self._ignore_next_voice_track_end: set[DiscordSnowflake] = set()

        self._voice_adapter.set_on_track_end_callback(self._on_voice_track_end)

    async def _on_voice_track_end(self, guild_id: DiscordSnowflake) -> None:
        if guild_id in self._ignore_next_voice_track_end:
            self._ignore_next_voice_track_end.discard(guild_id)
            logger.debug(LogTemplates.PLAYBACK_IGNORING_CALLBACK, guild_id)
            return

        session = await self._session_repo.get(guild_id)
        if session is None:
            return

        current_track = session.current_track
        if current_track:
            await self.handle_track_finished(guild_id, current_track)

    def set_track_finished_callback(self, callback: Callable[[DiscordSnowflake, Track], Any]) -> None:
        self._on_track_finished_callback = callback

    _MAX_RESOLVE_RETRIES: int = 3

    async def start_playback(
        self, guild_id: DiscordSnowflake, *, start_seconds: StartSeconds | None = None
    ) -> bool:
        """Start playback of the next track in queue.

        If stream-URL resolution fails, the track is discarded and the next
        track in the queue is tried, up to ``_MAX_RESOLVE_RETRIES`` times.
        """
        if start_seconds is not None:
            self._pending_start_seconds[guild_id] = start_seconds
        logger.info(LogTemplates.PLAYBACK_START_CALLED, guild_id)

        for attempt in range(self._MAX_RESOLVE_RETRIES):
            session = await self._session_repo.get(guild_id)
            if session is None:
                logger.warning(LogTemplates.SESSION_NOT_FOUND, guild_id)
                return False

            logger.info(
                "Session state=%s is_playing=%s has_current=%s queue_length=%s",
                session.state,
                session.is_playing,
                session.current_track is not None,
                session.queue_length,
            )

            if session.is_playing:
                logger.info(LogTemplates.PLAYBACK_ALREADY_PLAYING, guild_id)
                return True

            had_current = session.current_track is not None
            track = await self._get_next_track(session)
            if track is None:
                logger.warning(LogTemplates.QUEUE_NO_TRACKS, guild_id)
                return False

            logger.info(LogTemplates.TRACK_GOT_TO_PLAY, track.title)

            await self._persist_playback_state(
                guild_id,
                current_track=track,
                state=PlaybackState.IDLE,
                remove_from_queue=not had_current,
            )

            track = await self._ensure_stream_url(session, track, guild_id)
            if track is None:
                # Resolution failed — _ensure_stream_url already cleared current_track.
                # Loop back to try the next track in the queue.
                logger.warning(
                    LogTemplates.PLAYBACK_RESOLVE_RETRY,
                    track if track else "unknown",
                    guild_id,
                    attempt + 1,
                    self._MAX_RESOLVE_RETRIES,
                )
                continue

            return await self._start_voice_playback(session, track, guild_id)

        logger.error(
            LogTemplates.PLAYBACK_RESOLVE_RETRIES_EXHAUSTED,
            self._MAX_RESOLVE_RETRIES,
            guild_id,
        )
        return False

    async def _get_next_track(self, session: GuildPlaybackSession) -> Track | None:
        if session.current_track is not None:
            return session.current_track

        track = session.dequeue()
        if track is not None:
            session.set_current_track(track)
        return track

    async def _ensure_stream_url(
        self, session: GuildPlaybackSession, track: Track, guild_id: DiscordSnowflake
    ) -> Track | None:
        """Resolve and attach a stream URL. Returns None on failure (caller retries)."""
        if track.stream_url:
            return track

        try:
            resolved = await self._audio_resolver.resolve(track.webpage_url)
            if resolved is None:
                raise ValueError(ErrorMessages.RESOLVER_RETURNED_NONE)

            track = Track(
                id=track.id,
                title=resolved.title or track.title,
                webpage_url=track.webpage_url,
                stream_url=resolved.stream_url,
                duration_seconds=resolved.duration_seconds or track.duration_seconds,
                thumbnail_url=resolved.thumbnail_url or track.thumbnail_url,
                artist=resolved.artist or track.artist,
                uploader=resolved.uploader or track.uploader,
                like_count=resolved.like_count or track.like_count,
                view_count=resolved.view_count or track.view_count,
                requested_by_id=track.requested_by_id,
                requested_by_name=track.requested_by_name,
                requested_at=track.requested_at,
            )
            session.set_current_track(track)
            return track
        except Exception:
            logger.exception("Failed to resolve stream URL")
            session.set_current_track(None)
            await self._persist_playback_state(
                guild_id,
                current_track=None,
                state=PlaybackState.IDLE,
            )
            return None

    async def _start_voice_playback(
        self, session: GuildPlaybackSession, track: Track, guild_id: DiscordSnowflake
    ) -> bool:
        try:
            seek = self._pending_start_seconds.pop(guild_id, None)
            success = await self._voice_adapter.play(
                guild_id, track, start_seconds=seek
            )
            if not success:
                logger.error(LogTemplates.VOICE_ADAPTER_FAILED, guild_id)
                session.set_current_track(None)
                await self._persist_playback_state(
                    guild_id,
                    current_track=None,
                    state=PlaybackState.IDLE,
                )
                return False

            await self._persist_playback_state(
                guild_id,
                current_track=track,
                state=PlaybackState.PLAYING,
            )
            await self._history_repo.record_play(guild_id=guild_id, track=track)
            logger.info(LogTemplates.TRACK_STARTED, track.title, guild_id)

            from ...domain.shared.events import TrackStartedPlaying, get_event_bus

            await get_event_bus().publish(
                TrackStartedPlaying(
                    guild_id=guild_id,
                    track_id=track.id,
                    track_title=track.title,
                    track_url=track.webpage_url,
                    duration_seconds=track.duration_seconds,
                )
            )
            return True
        except Exception:
            logger.exception("Error starting playback")
            session.set_current_track(None)
            await self._persist_playback_state(
                guild_id,
                current_track=None,
                state=PlaybackState.IDLE,
            )
            return False

    async def stop_playback(self, guild_id: DiscordSnowflake) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None:
            return False

        self._ignore_next_voice_track_end.add(guild_id)
        try:
            await self._voice_adapter.stop(guild_id)
            session.stop()
            await self._persist_playback_state(
                guild_id,
                current_track=session.current_track,
                state=session.state,
            )
            logger.info(LogTemplates.PLAYBACK_STOPPED, guild_id)
            return True
        except Exception:
            # Stop failed — the voice callback may still fire normally,
            # so remove the suppression flag to avoid stalling the queue.
            self._ignore_next_voice_track_end.discard(guild_id)
            logger.exception("Error stopping playback")
            return False

    async def pause_playback(self, guild_id: DiscordSnowflake) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None or not session.is_playing:
            return False

        try:
            await self._voice_adapter.pause(guild_id)
            session.pause()
            await self._persist_playback_state(
                guild_id,
                current_track=session.current_track,
                state=session.state,
            )
            logger.debug(LogTemplates.PLAYBACK_PAUSED, guild_id)
            return True
        except Exception:
            logger.exception("Error pausing playback")
            return False

    async def resume_playback(self, guild_id: DiscordSnowflake) -> bool:
        session = await self._session_repo.get(guild_id)
        if session is None or not session.is_paused:
            return False

        try:
            await self._voice_adapter.resume(guild_id)
            session.resume()
            await self._persist_playback_state(
                guild_id,
                current_track=session.current_track,
                state=session.state,
            )
            logger.debug(LogTemplates.PLAYBACK_RESUMED, guild_id)
            return True
        except Exception:
            logger.exception("Error resuming playback")
            return False

    async def skip_track(self, guild_id: DiscordSnowflake) -> Track | None:
        """Skip the current track and return it, or None if nothing was playing."""
        session = await self._session_repo.get(guild_id)
        if session is None or session.current_track is None:
            return None

        skipped_track = session.current_track

        self._ignore_next_voice_track_end.add(guild_id)
        try:
            await self._voice_adapter.stop(guild_id)
        except Exception:
            self._ignore_next_voice_track_end.discard(guild_id)
            logger.exception("Error stopping voice during skip")
            return None

        next_track = session.advance_to_next_track()
        if next_track:
            session.state = PlaybackState.IDLE
        await self._session_repo.save(session)

        if next_track:
            await self.start_playback(guild_id)

        await self._history_repo.mark_finished(
            guild_id=guild_id,
            track_id=skipped_track.id,
            skipped=True,
        )

        logger.info(LogTemplates.TRACK_SKIPPED, skipped_track.title, guild_id)
        return skipped_track

    async def handle_track_finished(self, guild_id: DiscordSnowflake, track: Track) -> None:
        logger.debug(LogTemplates.TRACK_FINISHED, track.title, guild_id)

        session = await self._session_repo.get(guild_id)
        if session is None:
            return

        next_track = session.advance_to_next_track()
        if next_track:
            session.state = PlaybackState.IDLE
        await self._session_repo.save(session)

        if next_track:
            await self.start_playback(guild_id)
        else:
            logger.info(LogTemplates.QUEUE_EMPTY, guild_id)
            await get_event_bus().publish(
                QueueExhausted(
                    guild_id=guild_id,
                    last_track_id=track.id,
                    last_track_title=track.title,
                )
            )

        await self._history_repo.mark_finished(
            guild_id=guild_id,
            track_id=track.id,
            skipped=False,
        )

        if self._on_track_finished_callback:
            try:
                result = self._on_track_finished_callback(guild_id, track)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in track finished callback")

    def _handle_track_finished(self, guild_id: DiscordSnowflake, track: Track) -> None:
        asyncio.create_task(self.handle_track_finished(guild_id, track))

    def _tracks_match(self, left: Track, right: Track) -> bool:
        """Check whether two tracks refer to the same queued entry."""
        if left.requested_at and right.requested_at:
            return left.id == right.id and left.requested_at == right.requested_at
        return (
            left.id == right.id
            and left.webpage_url == right.webpage_url
            and left.requested_by_id == right.requested_by_id
        )

    def _remove_first_matching_track(self, queue: list[Track], target: Track) -> bool:
        for index, track in enumerate(queue):
            if self._tracks_match(track, target):
                queue.pop(index)
                return True
        return False

    async def _persist_playback_state(
        self,
        guild_id: DiscordSnowflake,
        *,
        current_track: Track | None,
        state: PlaybackState | None = None,
        remove_from_queue: bool = False,
    ) -> None:
        """Persist playback state without discarding concurrent queue updates."""
        session = await self._session_repo.get(guild_id)
        if session is None:
            return

        if remove_from_queue and current_track is not None:
            removed = self._remove_first_matching_track(session.queue, current_track)
            if not removed:
                logger.warning(
                    "Expected track not found in queue for guild %s during playback start",
                    guild_id,
                )

        session.current_track = current_track
        if state is not None:
            session.state = state
        session.touch()
        await self._session_repo.save(session)

    async def cleanup_guild(self, guild_id: DiscordSnowflake) -> None:
        """Release voice and session resources for a guild."""
        try:
            await self._voice_adapter.stop(guild_id)
            await self._voice_adapter.disconnect(guild_id)
        except Exception:
            logger.debug(LogTemplates.VOICE_CLEANUP_ERROR)

        await self._session_repo.delete(guild_id)
        logger.info(LogTemplates.SESSION_CLEANED_UP, guild_id)
