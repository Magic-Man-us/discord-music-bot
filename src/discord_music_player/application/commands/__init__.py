"""
Application Commands (CQRS Write Side)

Command objects and their handlers for write operations.
Commands represent intent to change the system state.
"""

from discord_music_player.application.commands.clear_queue import ClearQueueCommand
from discord_music_player.application.commands.play_track import PlayTrackCommand, PlayTrackResult
from discord_music_player.application.commands.skip_track import SkipResult, SkipTrackCommand
from discord_music_player.application.commands.stop_playback import StopPlaybackCommand
from discord_music_player.application.commands.vote_skip import VoteSkipCommand, VoteSkipResult

__all__ = [
    # Play
    "PlayTrackCommand",
    "PlayTrackResult",
    # Skip
    "SkipTrackCommand",
    "SkipResult",
    # Stop
    "StopPlaybackCommand",
    # Clear
    "ClearQueueCommand",
    # Vote
    "VoteSkipCommand",
    "VoteSkipResult",
]
