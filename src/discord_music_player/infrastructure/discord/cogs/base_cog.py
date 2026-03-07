"""Base cog with shared container initialization."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from ....config.container import Container


class BaseCog(commands.Cog):
    """Base class for cogs that need access to the DI container."""

    def __init__(self, bot: commands.Bot, container: Container) -> None:
        self.bot = bot
        self.container = container
