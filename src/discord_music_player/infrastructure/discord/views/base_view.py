"""Base class for interactive Discord views with common patterns."""

from __future__ import annotations

import discord

from ....utils.logging import get_logger

logger = get_logger(__name__)


class BaseInteractiveView(discord.ui.View):
    def __init__(self, *, timeout: float | None = 180.0) -> None:
        super().__init__(timeout=timeout)
        self._message: discord.Message | None = None
        self._resolved: bool = False

    def set_message(self, message: discord.Message) -> None:
        self._message = message

    def _disable_buttons(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

    def _disable_all_items(self) -> None:
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

    def _finish_view(self) -> bool:
        """Mark the view as resolved. Returns False if already resolved (race lost)."""
        if self._resolved:
            return False
        self._resolved = True
        self.stop()
        self._disable_buttons()
        return True

    async def _delete_message(self, *, delay: float | None = None) -> None:
        """Delete the tracked message from Discord. Safe to call if message is None or already gone."""
        if self._message is None:
            return
        try:
            await self._message.delete(delay=delay)
        except discord.HTTPException:
            logger.debug("Failed to delete view message %s", self._message.id)

    async def on_timeout(self) -> None:
        if not self._finish_view():
            return
        self._disable_all_items()
        await self._delete_message(delay=10.0)
