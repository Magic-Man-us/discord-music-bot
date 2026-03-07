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

__all__ = [
    "DomainError",
    "ValidationError",
    "EntityNotFoundError",
    "BusinessRuleViolationError",
    "ConcurrencyError",
    "InvalidOperationError",
]
