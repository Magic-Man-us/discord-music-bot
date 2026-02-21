"""Domain service for playback-related business rules."""

from __future__ import annotations

from discord_music_player.domain.music.entities import GuildPlaybackSession
from discord_music_player.domain.music.value_objects import PlaybackState
from discord_music_player.domain.shared.exceptions import BusinessRuleViolationError


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
