"""Base cog with shared container initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

import discord
from discord.ext import commands

from ....utils.logging import get_logger

if TYPE_CHECKING:
    from ....application.services.queue_models import BatchEnqueueResult
    from ....config.container import Container
    from ....domain.music.entities import Track


@runtime_checkable
class ContainerBot(Protocol):
    """Structural type for a Discord bot that carries the DI container."""

    container: Container | None

    async def add_cog(self, cog: commands.Cog, /) -> None: ...


class BaseCog(commands.Cog):
    """Base class for cogs that need access to the DI container."""

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container
        self.logger = get_logger(type(self).__module__)

    async def enqueue_and_start(
        self,
        interaction: discord.Interaction,
        tracks: list[Track],
    ) -> BatchEnqueueResult:
        """Enqueue a batch of tracks and start playback if needed."""
        assert interaction.guild is not None
        result = await self.container.queue_service.enqueue_batch(
            guild_id=interaction.guild.id,
            tracks=tracks,
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
        )
        if result.should_start:
            # No now-playing embed is sent by batch callers (they post an
            # ephemeral summary), so let the TrackStartedPlaying auto-poster
            # publish the now-playing embed — do NOT reserve here.
            await self.container.playback_service.start_playback(interaction.guild.id)
        return result

    @classmethod
    async def setup(cls, bot: commands.Bot) -> None:
        """Standard cog setup — registers the cog with the bot's container."""
        if not isinstance(bot, ContainerBot) or bot.container is None:
            raise RuntimeError(f"{cls.__name__}: container not found on bot instance")
        await bot.add_cog(cls(bot, bot.container))
