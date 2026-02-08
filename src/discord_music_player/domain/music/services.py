"""Domain services for cross-entity music business logic."""

from __future__ import annotations

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import LoopMode, PlaybackState
from discord_music_player.domain.shared.exceptions import BusinessRuleViolationError


class QueueDomainService:
    """Domain service for queue-related business rules."""

    MAX_QUEUE_SIZE = 50
    MAX_TRACK_DURATION_SECONDS = 3 * 60 * 60

    @classmethod
    def can_enqueue(cls, session: GuildPlaybackSession) -> bool:
        return session.queue_length < cls.MAX_QUEUE_SIZE

    @classmethod
    def validate_track_duration(cls, track: Track) -> bool:
        """Return True if the track's duration is acceptable or unknown."""
        if track.duration_seconds is None:
            return True
        return track.duration_seconds <= cls.MAX_TRACK_DURATION_SECONDS

    @classmethod
    def get_next_track(cls, session: GuildPlaybackSession) -> Track | None:
        """Determine the next track based on queue and loop mode."""
        if session.loop_mode == LoopMode.TRACK and session.current_track:
            return session.current_track

        return session.peek()

    @classmethod
    def calculate_queue_position(cls, session: GuildPlaybackSession) -> int:
        return session.queue_length

    @classmethod
    def get_queue_duration(cls, session: GuildPlaybackSession) -> int | None:
        """Return total queue duration in seconds, or None if any track has unknown duration."""
        total = 0
        for track in session.queue:
            if track.duration_seconds is None:
                return None
            total += track.duration_seconds
        return total

    @classmethod
    def format_queue_duration(cls, session: GuildPlaybackSession) -> str:
        """Format the total queue duration as a human-readable string."""
        duration = cls.get_queue_duration(session)
        if duration is None:
            return "Unknown"

        hours, remainder = divmod(duration, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    @classmethod
    def should_auto_play_next(cls, session: GuildPlaybackSession) -> bool:
        """Determine if auto-play should continue to the next track."""
        if session.state == PlaybackState.STOPPED:
            return False

        if session.queue:
            return True

        if session.loop_mode == LoopMode.QUEUE and session.current_track:
            return True

        return False


class PlaybackDomainService:
    """Domain service for playback-related business rules."""

    @staticmethod
    def can_start_playback(session: GuildPlaybackSession) -> bool:
        if not session.current_track and not session.queue:
            return False

        if session.state == PlaybackState.PLAYING:
            return False

        return True

    @staticmethod
    def can_pause(session: GuildPlaybackSession) -> bool:
        return session.state == PlaybackState.PLAYING

    @staticmethod
    def can_resume(session: GuildPlaybackSession) -> bool:
        return session.state == PlaybackState.PAUSED

    @staticmethod
    def can_skip(session: GuildPlaybackSession) -> bool:
        return session.current_track is not None

    @staticmethod
    def validate_state_transition(session: GuildPlaybackSession, new_state: PlaybackState) -> None:
        """Validate a state transition is allowed."""
        if not session.state.can_transition_to(new_state):
            raise BusinessRuleViolationError(
                rule="STATE_TRANSITION",
                message=f"Cannot transition from {session.state.value} to {new_state.value}",
            )
