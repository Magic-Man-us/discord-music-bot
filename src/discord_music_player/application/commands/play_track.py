"""Command and handler for playing a track from a query or URL."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

from discord_music_player.domain.music.entities import Track
from discord_music_player.domain.shared.validators import (
    DiscordValidators,
    validate_non_empty_string,
)

if TYPE_CHECKING:
    from ...domain.music.repository import SessionRepository
    from ..interfaces.audio_resolver import AudioResolver
    from ..interfaces.voice_adapter import VoiceAdapter


class PlayTrackStatus(Enum):
    """Status codes for play track results."""

    SUCCESS = "success"
    QUEUED = "queued"
    NOW_PLAYING = "now_playing"
    TRACK_NOT_FOUND = "track_not_found"
    RESOLUTION_ERROR = "resolution_error"
    VOICE_ERROR = "voice_error"
    QUEUE_FULL = "queue_full"
    PERMISSION_DENIED = "permission_denied"


class PlayTrackCommand(BaseModel):
    """Request to resolve a query/URL, queue the track, and optionally start playback."""

    model_config = ConfigDict(frozen=True, strict=True)

    guild_id: int
    channel_id: int
    user_id: int
    user_name: str
    query: str

    play_next: bool = False
    want_recommendations: bool = False
    start_playing: bool = True
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    _validate_ids = DiscordValidators.snowflakes("guild_id", "channel_id", "user_id")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        return validate_non_empty_string(v, "Query")


class PlayTrackResult(BaseModel):
    """Result of a play track command."""

    model_config = ConfigDict(frozen=True, strict=True)

    status: PlayTrackStatus
    message: str
    track: Track | None = None
    queue_position: int | None = None
    queue_length: int = 0
    started_playing: bool = False
    recommendations_requested: bool = False

    @property
    def is_success(self) -> bool:
        return self.status in {
            PlayTrackStatus.SUCCESS,
            PlayTrackStatus.QUEUED,
            PlayTrackStatus.NOW_PLAYING,
        }

    @classmethod
    def success(
        cls,
        track: Track,
        queue_position: int,
        queue_length: int,
        started_playing: bool = False,
        recommendations_requested: bool = False,
    ) -> PlayTrackResult:
        if started_playing:
            status = PlayTrackStatus.NOW_PLAYING
            message = f"Now playing: {track.title}"
        else:
            status = PlayTrackStatus.QUEUED
            message = f"Added to queue: {track.title} (position {queue_position + 1})"

        return cls(
            status=status,
            message=message,
            track=track,
            queue_position=queue_position,
            queue_length=queue_length,
            started_playing=started_playing,
            recommendations_requested=recommendations_requested,
        )

    @classmethod
    def error(cls, status: PlayTrackStatus, message: str) -> PlayTrackResult:
        return cls(status=status, message=message)


class PlayTrackHandler:
    """Resolves a track from a query, adds it to the queue, and starts playback if needed."""

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        audio_resolver: AudioResolver,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repo = session_repository
        self._audio_resolver = audio_resolver
        self._voice_adapter = voice_adapter

    async def handle(self, command: PlayTrackCommand) -> PlayTrackResult:
        voice_result = await self._voice_adapter.ensure_connected(
            command.guild_id, command.channel_id
        )
        if not voice_result:
            return PlayTrackResult.error(
                PlayTrackStatus.VOICE_ERROR, "Could not connect to voice channel"
            )

        try:
            track = await self._audio_resolver.resolve(command.query)
            if track is None:
                return PlayTrackResult.error(
                    PlayTrackStatus.TRACK_NOT_FOUND, f"Could not find track: {command.query}"
                )
        except Exception as e:
            return PlayTrackResult.error(
                PlayTrackStatus.RESOLUTION_ERROR, f"Error resolving track: {e}"
            )

        track = track.with_requester(
            user_id=command.user_id,
            user_name=command.user_name,
            requested_at=command.requested_at,
        )

        session = await self._session_repo.get_or_create(command.guild_id)

        if not session.can_add_to_queue:
            return PlayTrackResult.error(PlayTrackStatus.QUEUE_FULL, "Queue is full")

        if command.play_next:
            position = session.enqueue_next(track)
        else:
            position = session.enqueue(track)

        await self._session_repo.save(session)

        started_playing = False
        if command.start_playing and session.is_idle:
            # Playback will be triggered by the application service
            started_playing = True

        return PlayTrackResult.success(
            track=track,
            queue_position=position.value,
            queue_length=session.queue_length,
            started_playing=started_playing,
            recommendations_requested=command.want_recommendations,
        )
