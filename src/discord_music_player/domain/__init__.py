# ruff: noqa: N999
"""
Domain Layer

Contains pure business logic organized by bounded contexts:
- shared/: Cross-cutting value objects and exceptions
- music/: Track, queue, and playback domain logic
- voting/: Vote session and voting rules
- recommendations/: AI recommendation domain logic
"""

from .shared.exceptions import DomainError

__all__ = [
    "DomainError",
]
