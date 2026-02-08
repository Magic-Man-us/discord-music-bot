"""
Application Queries (CQRS Read Side)

Query objects and handlers for read operations.
Queries do not modify state, only retrieve data.
"""

from discord_music_player.application.queries.get_current import (
    CurrentTrackInfo,
    GetCurrentTrackQuery,
)
from discord_music_player.application.queries.get_queue import GetQueueQuery, QueueInfo

__all__ = [
    "GetQueueQuery",
    "QueueInfo",
    "GetCurrentTrackQuery",
    "CurrentTrackInfo",
]
