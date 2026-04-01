"""
Application Commands (CQRS Write Side)

Command objects and their handlers for write operations.
Commands represent intent to change the system state.
"""

from .vote_skip import VoteSkipCommand, VoteSkipResult

__all__ = [
    "VoteSkipCommand",
    "VoteSkipResult",
]
