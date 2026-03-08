"""Base cog with shared container initialization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from ....config.container import Container


class BaseCog(commands.Cog):
    """Base class for cogs that need access to the DI container."""

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container
        self.logger = logging.getLogger(type(self).__module__)

    @classmethod
    async def setup(cls, bot: commands.Bot) -> None:
        """Standard cog setup — extracts the container from the bot and registers the cog."""
        container: Container | None = getattr(bot, "container", None)
        if container is None:
            raise RuntimeError(f"{cls.__name__}: container not found on bot instance")
        await bot.add_cog(cls(bot, container))
