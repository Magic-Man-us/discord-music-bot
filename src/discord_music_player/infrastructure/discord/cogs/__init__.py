"""Discord cogs - command handlers."""

from discord_music_player.infrastructure.discord.cogs.admin_cog import AdminCog
from discord_music_player.infrastructure.discord.cogs.analytics_cog import AnalyticsCog
from discord_music_player.infrastructure.discord.cogs.event_cog import EventCog
from discord_music_player.infrastructure.discord.cogs.health_cog import HealthCog
from discord_music_player.infrastructure.discord.cogs.info_cog import InfoCog
from discord_music_player.infrastructure.discord.cogs.music_cog import MusicCog

__all__ = [
    "MusicCog",
    "AdminCog",
    "AnalyticsCog",
    "HealthCog",
    "InfoCog",
    "EventCog",
]
