"""
Voting Bounded Context

Domain logic for skip voting, stop voting, and other polling mechanisms.
"""

from discord_music_player.domain.voting.entities import Vote, VoteSession
from discord_music_player.domain.voting.repository import VoteSessionRepository
from discord_music_player.domain.voting.services import VotingDomainService
from discord_music_player.domain.voting.value_objects import VoteResult, VoteType

__all__ = [
    # Entities
    "Vote",
    "VoteSession",
    # Value Objects
    "VoteType",
    "VoteResult",
    # Repository
    "VoteSessionRepository",
    # Services
    "VotingDomainService",
]
