"""Discord cogs - command handlers."""

from discord_music_player.infrastructure.discord.cogs.admin_cog import AdminCog
from discord_music_player.infrastructure.discord.cogs.analytics_cog import AnalyticsCog
from discord_music_player.infrastructure.discord.cogs.event_cog import EventCog
from discord_music_player.infrastructure.discord.cogs.health_cog import HealthCog
from discord_music_player.infrastructure.discord.cogs.info_cog import InfoCog
from discord_music_player.infrastructure.discord.cogs.now_playing_cog import NowPlayingCog
from discord_music_player.infrastructure.discord.cogs.playback_cog import PlaybackCog
from discord_music_player.infrastructure.discord.cogs.queue_cog import QueueCog
from discord_music_player.infrastructure.discord.cogs.radio_cog import RadioCog
from discord_music_player.infrastructure.discord.cogs.skip_cog import SkipCog

__all__ = [
    "PlaybackCog",
    "QueueCog",
    "SkipCog",
    "RadioCog",
    "NowPlayingCog",
    "AdminCog",
    "AnalyticsCog",
    "HealthCog",
    "InfoCog",
    "EventCog",
]
