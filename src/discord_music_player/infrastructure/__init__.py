"""Infrastructure layer - external systems integration.

This layer contains implementations for:
- Persistence (SQLite repositories)
- Discord (bot, cogs, adapters)
- Audio (yt-dlp, FFmpeg)
- AI (pydantic-ai multi-provider)
- Logging configuration
"""

from discord_music_player.infrastructure.discord.bot import create_bot
from discord_music_player.infrastructure.discord.adapters.voice_adapter import DiscordVoiceAdapter
from discord_music_player.infrastructure.persistence.database import Database

__all__ = [
    "create_bot",
    "DiscordVoiceAdapter",
    "Database",
]
