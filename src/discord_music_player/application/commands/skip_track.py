"""Command and handler for skipping the current track."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from discord_music_player.domain.shared.types import DiscordSnowflake

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


class SkipTrackCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    guild_id: DiscordSnowflake
    user_id: DiscordSnowflake
    user_channel_id: DiscordSnowflake | None = None
    force: bool = False


class SkipResult(BaseModel):

    status: SkipStatus
    message: str
    skipped_track: Track | None = None
    next_track: Track | None = None
    requires_vote: bool = False

    @property
    def is_success(self) -> bool:
        return self.status == SkipStatus.SUCCESS

    @classmethod
    def success(cls, skipped_track: Track, next_track: Track | None = None) -> SkipResult:
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
        return cls(
            status=SkipStatus.PERMISSION_DENIED,
            message="Vote required to skip. Use the vote-skip command.",
            requires_vote=True,
        )

    @classmethod
    def error(cls, status: SkipStatus, message: str) -> SkipResult:
        return cls(status=status, message=message)


class SkipTrackHandler:
    """Skips the current track with permission checks, falling back to vote-skip."""

    def __init__(
        self,
        *,
        session_repository: SessionRepository,
        voice_adapter: VoiceAdapter,
    ) -> None:
        self._session_repo = session_repository
        self._voice_adapter = voice_adapter

    async def handle(self, command: SkipTrackCommand) -> SkipResult:
        session = await self._session_repo.get(command.guild_id)
        if session is None or session.current_track is None:
            return SkipResult.error(SkipStatus.NOTHING_PLAYING, "Nothing is currently playing")

        current_track = session.current_track

        if not command.force:
            if command.user_channel_id is None:
                return SkipResult.error(
                    SkipStatus.NOT_IN_CHANNEL, "You must be in a voice channel to skip"
                )

            listeners = await self._voice_adapter.get_listeners(command.guild_id)
            listener_count = len(listeners)

            if not current_track.was_requested_by(command.user_id):
                # Small audience rule: skip freely with 2 or fewer listeners
                if listener_count > 2:
                    return SkipResult.requires_voting()

        skipped_track = current_track
        next_track = session.advance_to_next_track()

        await self._voice_adapter.stop(command.guild_id)
        await self._session_repo.save(session)

        return SkipResult.success(skipped_track, next_track)
