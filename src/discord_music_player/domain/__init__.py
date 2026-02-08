# ruff: noqa: N999
"""
Domain Layer

Contains pure business logic organized by bounded contexts:
- shared/: Cross-cutting value objects and exceptions
- music/: Track, queue, and playback domain logic
- voting/: Vote session and voting rules
- recommendations/: AI recommendation domain logic
"""

from discord_music_player.domain.shared import ChannelId, GuildId, UserId
from discord_music_player.domain.shared.exceptions import DomainError

__all__ = [
    "GuildId",
    "UserId",
    "ChannelId",
    "DomainError",
]
