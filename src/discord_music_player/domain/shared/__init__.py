"""
Shared Domain Kernel

Contains value objects and exceptions shared across all bounded contexts.
"""

from discord_music_player.domain.shared.exceptions import (
    BusinessRuleViolationError,
    ConcurrencyError,
    DomainError,
    EntityNotFoundError,
    InvalidOperationError,
    ValidationError,
)
from discord_music_player.domain.shared.value_objects import ChannelId, GuildId, UserId

__all__ = [
    "GuildId",
    "UserId",
    "ChannelId",
    "DomainError",
    "ValidationError",
    "EntityNotFoundError",
    "BusinessRuleViolationError",
    "ConcurrencyError",
    "InvalidOperationError",
]
