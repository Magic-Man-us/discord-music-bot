"""
Skip Track Command

Command and handler for skipping the current track.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.music.entities import Track
    from ...domain.music.repository import SessionRepository
    from ..interfaces.voice_adapter import VoiceAdapter


class SkipStatus(Enum):
    """Status codes for skip results."""

    SUCCESS = "success"
    NOTHING_PLAYING = "nothing_playing"
    NOT_IN_CHANNEL = "not_in_channel"
    PERMISSION_DENIED = "permission_denied"
    ERROR = "error"


@dataclass
class SkipTrackCommand:
    """Command to skip the current track.

    Supports both immediate skip (for authorized users) and
    indicates if this should trigger vote-skip instead.
    """

    guild_id: int
    user_id: int
    user_channel_id: int | None = None  # User's current voice channel
    force: bool = False  # Skip without voting (for DJs/admins)

    def __post_init__(self) -> None:
        if self.guild_id <= 0:
            raise ValueError("Guild ID must be positive")
        if self.user_id <= 0:
            raise ValueError("User ID must be positive")


@dataclass
class SkipResult:
    """Result of a skip track command."""

    status: SkipStatus
    message: str
    skipped_track: Track | None = None
    next_track: Track | None = None
    requires_vote: bool = False

    @property
    def is_success(self) -> bool:
        """Check if the skip was successful."""
        return self.status == SkipStatus.SUCCESS

    @classmethod
    def success(cls, skipped_track: Track, next_track: Track | None = None) -> SkipResult:
        """Create a successful skip result."""
        if next_track:
            message = f"Skipped: {skipped_track.title}. Now playing: {next_track.title}"
        else:
            message = f"Skipped: {skipped_track.title}. Queue is now empty."

        return cls(
            status=SkipStatus.SUCCESS,
            message=message,
            skipped_track=skipped_track,
            next_track=next_track,
        )

    @classmethod
    def requires_voting(cls) -> SkipResult:
        """Create a result indicating voting is required."""
        return cls(
            status=SkipStatus.PERMISSION_DENIED,
            message="Vote required to skip. Use the vote-skip command.",
            requires_vote=True,
        )

    @classmethod
    def error(cls, status: SkipStatus, message: str) -> SkipResult:
        """Create an error result."""
        return cls(status=status, message=message)


class SkipTrackHandler:
    """Handler for SkipTrackCommand.

    Handles the logic for skipping tracks, including permission
    checks and transitioning to the next track.
    """

    def __init__(
        self,
        session_repository: SessionRepository,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repository = session_repository
        self._voice_adapter = voice_adapter

    async def handle(self, command: SkipTrackCommand) -> SkipResult:
        """Execute the skip track command.

        Args:
            command: The skip track command.

        Returns:
            The result of the operation.
        """
        # Get session
        session = await self._session_repository.get(command.guild_id)
        if session is None or session.current_track is None:
            return SkipResult.error(SkipStatus.NOTHING_PLAYING, "Nothing is currently playing")

        current_track = session.current_track

        # Check if user can skip
        if not command.force:
            # Check if user is in the voice channel
            if command.user_channel_id is None:
                return SkipResult.error(
                    SkipStatus.NOT_IN_CHANNEL, "You must be in a voice channel to skip"
                )

            # Get listener count
            listeners = await self._voice_adapter.get_listeners(command.guild_id)
            listener_count = len(listeners)

            # Allow requester to skip their own track
            if not current_track.was_requested_by(command.user_id):
                # Check for small audience rule (2 or fewer listeners)
                if listener_count > 2:
                    return SkipResult.requires_voting()

        # Perform skip
        skipped_track = current_track
        next_track = session.advance_to_next_track()

        # Stop current playback
        await self._voice_adapter.stop(command.guild_id)

        # Save session
        await self._session_repository.save(session)

        return SkipResult.success(skipped_track, next_track)
