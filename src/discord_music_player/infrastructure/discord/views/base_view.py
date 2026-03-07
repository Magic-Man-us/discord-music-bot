"""Base class for interactive Discord views with common patterns."""

from __future__ import annotations

import discord


class BaseInteractiveView(discord.ui.View):
    """Base view providing message tracking and button disabling."""

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
