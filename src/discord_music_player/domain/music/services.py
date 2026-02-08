"""
Music Domain Services

Domain services containing business logic that doesn't naturally fit
within a single entity or value object.
"""

from __future__ import annotations

from discord_music_player.domain.music.entities import GuildPlaybackSession, Track
from discord_music_player.domain.music.value_objects import LoopMode, PlaybackState
from discord_music_player.domain.shared.exceptions import BusinessRuleViolationError


class QueueDomainService:
    """Domain service for queue-related business rules.

    This service encapsulates complex queue operations and rules
    that span multiple entities or require external information.
    """

    # Configuration
    MAX_QUEUE_SIZE = 50
    MAX_TRACK_DURATION_SECONDS = 3 * 60 * 60  # 3 hours

    @classmethod
    def can_enqueue(cls, session: GuildPlaybackSession) -> bool:
        """Check if more tracks can be added to the queue.

        Args:
            session: The guild playback session.

        Returns:
            True if tracks can be added.
        """
        return session.queue_length < cls.MAX_QUEUE_SIZE

    @classmethod
    def validate_track_duration(cls, track: Track) -> bool:
        """Validate that a track's duration is acceptable.

        Args:
            track: The track to validate.

        Returns:
            True if duration is acceptable or unknown.
        """
        if track.duration_seconds is None:
            return True
        return track.duration_seconds <= cls.MAX_TRACK_DURATION_SECONDS

    @classmethod
    def get_next_track(cls, session: GuildPlaybackSession) -> Track | None:
        """Determine the next track to play based on queue and loop mode.

        Args:
            session: The guild playback session.

        Returns:
            The next track to play, or None if no tracks available.
        """
        if session.loop_mode == LoopMode.TRACK and session.current_track:
            return session.current_track

        return session.peek()

    @classmethod
    def calculate_queue_position(cls, session: GuildPlaybackSession) -> int:
        """Calculate the position where a new track would be added.

        Args:
            session: The guild playback session.

        Returns:
            The position index for a new track.
        """
        return session.queue_length

    @classmethod
    def get_queue_duration(cls, session: GuildPlaybackSession) -> int | None:
        """Calculate total duration of all tracks in the queue.

        Args:
            session: The guild playback session.

        Returns:
            Total duration in seconds, or None if any track has unknown duration.
        """
        total = 0
        for track in session.queue:
            if track.duration_seconds is None:
                return None
            total += track.duration_seconds
        return total

    @classmethod
    def format_queue_duration(cls, session: GuildPlaybackSession) -> str:
        """Format the total queue duration as a human-readable string.

        Args:
            session: The guild playback session.

        Returns:
            Formatted duration string.
        """
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
        """Determine if auto-play should continue to the next track.

        Args:
            session: The guild playback session.

        Returns:
            True if auto-play should continue.
        """
        # Don't auto-play if stopped
        if session.state == PlaybackState.STOPPED:
            return False

        # Check if there are more tracks
        if session.queue:
            return True

        # Check loop mode
        if session.loop_mode == LoopMode.QUEUE and session.current_track:
            return True

        return False


class PlaybackDomainService:
    """Domain service for playback-related business rules."""

    @staticmethod
    def can_start_playback(session: GuildPlaybackSession) -> bool:
        """Check if playback can be started.

        Args:
            session: The guild playback session.

        Returns:
            True if playback can be started.
        """
        # Must have a track to play
        if not session.current_track and not session.queue:
            return False

        # Can't start if already playing
        if session.state == PlaybackState.PLAYING:
            return False

        return True

    @staticmethod
    def can_pause(session: GuildPlaybackSession) -> bool:
        """Check if playback can be paused.

        Args:
            session: The guild playback session.

        Returns:
            True if playback can be paused.
        """
        return session.state == PlaybackState.PLAYING

    @staticmethod
    def can_resume(session: GuildPlaybackSession) -> bool:
        """Check if playback can be resumed.

        Args:
            session: The guild playback session.

        Returns:
            True if playback can be resumed.
        """
        return session.state == PlaybackState.PAUSED

    @staticmethod
    def can_skip(session: GuildPlaybackSession) -> bool:
        """Check if current track can be skipped.

        Args:
            session: The guild playback session.

        Returns:
            True if there's a current track to skip.
        """
        return session.current_track is not None

    @staticmethod
    def validate_state_transition(session: GuildPlaybackSession, new_state: PlaybackState) -> None:
        """Validate a state transition is allowed.

        Args:
            session: The guild playback session.
            new_state: The target state.

        Raises:
            BusinessRuleViolation: If the transition is not allowed.
        """
        if not session.state.can_transition_to(new_state):
            raise BusinessRuleViolationError(
                rule="STATE_TRANSITION",
                message=f"Cannot transition from {session.state.value} to {new_state.value}",
            )
