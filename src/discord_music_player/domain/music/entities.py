"""Core domain entities for the music bounded context."""

from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LoopMode, PlaybackState
from .wrappers import QueuePosition, TrackId
from ..shared.constants import LimitConstants
from ..shared.datetime_utils import UtcDateTime, utcnow
from ..shared.exceptions import (
    BusinessRuleViolationError,
    InvalidOperationError,
)
from ..shared.types import (
    DiscordSnowflake,
    DurationSeconds,
    HttpUrlStr,
    NonEmptyStr,
    NonNegativeInt,
    QueuePositionInt,
    TrackTitleStr,
    UtcDatetimeField,
)

_RESOLVE_EXCLUDE_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "requested_by_id",
        "requested_by_name",
        "requested_at",
        "is_from_recommendation",
    }
)


class PlaylistEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: TrackTitleStr
    url: HttpUrlStr
    duration_seconds: DurationSeconds | None = None


class Track(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    id: TrackId
    title: TrackTitleStr
    webpage_url: HttpUrlStr
    stream_url: HttpUrlStr | None = None
    duration_seconds: DurationSeconds | None = None
    thumbnail_url: HttpUrlStr | None = None
    artist: NonEmptyStr | None = None
    uploader: NonEmptyStr | None = None
    like_count: NonNegativeInt | None = None
    view_count: NonNegativeInt | None = None
    requested_by_id: DiscordSnowflake | None = None
    requested_by_name: NonEmptyStr | None = None
    requested_at: UtcDatetimeField | None = None
    is_from_recommendation: bool = False
    is_direct_request: bool = False

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_track_id(cls, v: Any) -> TrackId:
        if isinstance(v, str):
            return TrackId(value=v)
        if isinstance(v, dict):
            return TrackId.model_validate(v)
        return v

    @field_validator("requested_at", mode="before")
    @classmethod
    def _coerce_requested_at(cls, v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, str):
            return UtcDateTime.from_iso(v).dt
        return v

    @property
    def duration_formatted(self) -> str:
        if self.duration_seconds is None:
            return "Unknown"

        hours, remainder = divmod(self.duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def display_title(self) -> str:
        if self.duration_seconds:
            return f"{self.title} [{self.duration_formatted}]"
        return self.title

    def with_requester(
        self,
        user_id: DiscordSnowflake,
        user_name: NonEmptyStr,
        requested_at: datetime | None = None,
    ) -> Track:
        return self.model_copy(
            update={
                "requested_by_id": user_id,
                "requested_by_name": user_name,
                "requested_at": requested_at or utcnow(),
            }
        )

    def with_resolved(self, resolved: Track) -> Track:
        """Merge resolver data onto this track, preserving requester metadata and identity."""
        resolved_dump = resolved.model_dump(
            exclude_none=True,
            exclude=_RESOLVE_EXCLUDE_FIELDS,
        )
        return self.model_copy(update=resolved_dump)

    def was_requested_by(self, user_id: DiscordSnowflake) -> bool:
        return self.requested_by_id == user_id


class GuildPlaybackSession(BaseModel):
    model_config = ConfigDict(strict=True)

    MAX_QUEUE_SIZE: ClassVar[int] = LimitConstants.MAX_QUEUE_SIZE

    guild_id: DiscordSnowflake
    queue: list[Track] = Field(default_factory=list)
    current_track: Track | None = None
    state: PlaybackState = PlaybackState.IDLE
    loop_mode: LoopMode = LoopMode.OFF
    created_at: UtcDatetimeField = Field(default_factory=utcnow)
    last_activity: UtcDatetimeField = Field(default_factory=utcnow)
    playback_started_at: UtcDatetimeField | None = None

    @property
    def elapsed_seconds(self) -> int:
        """Seconds elapsed since playback started, or 0 if not playing."""
        if self.playback_started_at is None:
            return 0
        return max(0, int((utcnow() - self.playback_started_at).total_seconds()))

    @property
    def queue_length(self) -> int:
        return len(self.queue)

    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING

    @property
    def is_paused(self) -> bool:
        return self.state == PlaybackState.PAUSED

    @property
    def is_idle(self) -> bool:
        return self.state == PlaybackState.IDLE

    @property
    def has_tracks(self) -> bool:
        return self.current_track is not None or bool(self.queue)

    @property
    def can_add_to_queue(self) -> bool:
        return self.queue_length < self.MAX_QUEUE_SIZE

    def touch(self) -> None:
        self.last_activity = utcnow()

    def is_duplicate(self, track: Track) -> bool:
        if self.current_track and self.current_track.id == track.id:
            return True
        return any(t.id == track.id for t in self.queue)

    def _assert_can_enqueue(self, track: Track) -> None:
        if self.is_duplicate(track):
            raise BusinessRuleViolationError(
                rule="NO_DUPLICATES",
                message=f'"{track.title}" is already in the queue or currently playing',
            )
        if not self.can_add_to_queue:
            raise BusinessRuleViolationError(
                rule="MAX_QUEUE_SIZE", message=f"Queue is full (max {self.MAX_QUEUE_SIZE} tracks)"
            )

    def enqueue(self, track: Track) -> QueuePosition:
        self._assert_can_enqueue(track)
        position = QueuePosition(value=len(self.queue))
        self.queue.append(track)
        self.touch()
        return position

    def enqueue_next(self, track: Track) -> QueuePosition:
        self._assert_can_enqueue(track)
        self.queue.insert(0, track)
        self.touch()
        return QueuePosition(value=0)

    def dequeue(self) -> Track | None:
        if not self.queue:
            return None

        track = self.queue.pop(0)
        self.touch()
        return track

    def peek(self) -> Track | None:
        return self.queue[0] if self.queue else None

    def remove_at(self, position: QueuePositionInt) -> Track | None:
        if 0 <= position < len(self.queue):
            track = self.queue.pop(position)
            self.touch()
            return track
        return None

    def clear_queue(self) -> int:
        count = len(self.queue)
        self.queue.clear()
        self.touch()
        return count

    def clear_recommendations(self) -> int:
        original_count = len(self.queue)
        self.queue = [track for track in self.queue if not track.is_from_recommendation]
        removed_count = original_count - len(self.queue)
        if removed_count > 0:
            self.touch()
        return removed_count

    def set_current_track(self, track: Track | None) -> None:
        self.current_track = track
        self.touch()

    def transition_to(self, new_state: PlaybackState) -> None:
        if not self.state.can_transition_to(new_state):
            raise InvalidOperationError(
                operation=f"transition to {new_state.value}",
                current_state=self.state.value,
                message=f"Cannot transition from {self.state.value} to {new_state.value}",
            )

        self.state = new_state
        self.touch()

    def start_playback(self, track: Track) -> None:
        self.current_track = track
        if self.state.can_transition_to(PlaybackState.PLAYING):
            self.transition_to(PlaybackState.PLAYING)
        self.touch()

    def pause(self) -> None:
        self.transition_to(PlaybackState.PAUSED)

    def resume(self) -> None:
        self.transition_to(PlaybackState.PLAYING)

    def stop(self) -> None:
        self.transition_to(PlaybackState.STOPPED)
        self.current_track = None

    def reset(self) -> None:
        self.state = PlaybackState.IDLE
        self.current_track = None
        self.queue.clear()
        self.touch()

    def advance_to_next_track(self) -> Track | None:
        """Handles loop modes: TRACK re-plays current, QUEUE appends current to end."""
        if self.loop_mode == LoopMode.TRACK and self.current_track:
            return self.current_track

        if self.loop_mode == LoopMode.QUEUE and self.current_track:
            self.queue.append(self.current_track)

        next_track = self.dequeue()
        self.current_track = next_track

        if next_track is None and self.state != PlaybackState.IDLE:
            self.transition_to(PlaybackState.IDLE)

        return next_track

    def toggle_loop(self) -> LoopMode:
        self.loop_mode = self.loop_mode.next_mode()
        self.touch()
        return self.loop_mode

    def shuffle(self) -> None:
        import random

        random.shuffle(self.queue)
        self.touch()

    def move_track(self, from_pos: QueuePositionInt, to_pos: QueuePositionInt) -> bool:
        if not (0 <= from_pos < len(self.queue) and 0 <= to_pos < len(self.queue)):
            return False

        track = self.queue.pop(from_pos)
        self.queue.insert(to_pos, track)
        self.touch()
        return True

    def prepare_for_resume(self) -> int:
        """Prepare session for resume after bot restart.

        Resets state to IDLE, clears stale stream URLs (tokens expire),
        and captures elapsed seconds before clearing playback timestamp.

        Returns the elapsed seconds at the time of preparation.
        """
        elapsed = self.elapsed_seconds
        self.state = PlaybackState.IDLE
        self.playback_started_at = None
        if self.current_track is not None:
            self.current_track = self.current_track.model_copy(
                update={"stream_url": None},
            )
        self.queue = [
            track.model_copy(update={"stream_url": None}) for track in self.queue
        ]
        self.touch()
        return elapsed
