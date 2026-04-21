"""View with a retry button for voice channel warmup."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

import discord
from pydantic import BaseModel, ConfigDict

from ....utils.logging import get_logger
from .base_view import BaseInteractiveView

logger = get_logger(__name__)


class ReplayCallback(Protocol):
    async def __call__(self, interaction: discord.Interaction) -> None: ...


ReplayFn = Callable[[discord.Interaction], Awaitable[None]]


class WarmupRetryState(BaseModel):
    """``replay`` is a pre-baked coroutine that carries every /play param the
    user originally supplied (query, count, start, shuffle, seek). The view
    just invokes it on retry — no per-param plumbing needed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    remaining_seconds: int
    query: str
    replay: ReplayFn


class WarmupRetryView(BaseInteractiveView):
    def __init__(self, state: WarmupRetryState) -> None:
        super().__init__(timeout=state.remaining_seconds + 120)
        self._state = state
        self._enable_task: asyncio.Task[None] | None = None

    def set_message(self, message: discord.Message) -> None:
        super().set_message(message)
        self._enable_task = asyncio.create_task(self._enable_after_warmup())

    async def _enable_after_warmup(self) -> None:
        try:
            await asyncio.sleep(self._state.remaining_seconds)
        except asyncio.CancelledError:
            return

        self.retry_button.disabled = False
        self.retry_button.style = discord.ButtonStyle.primary
        if self._message is not None:
            try:
                await self._message.edit(
                    content="You can now use commands! Click **Retry** to play.",
                    view=self,
                )
            except discord.HTTPException:
                logger.debug("Failed to edit warmup retry message")

    @discord.ui.button(label="Retry", style=discord.ButtonStyle.secondary, disabled=True)
    async def retry_button(
        self, interaction: discord.Interaction, _button: discord.ui.Button[WarmupRetryView]
    ) -> None:
        if not self._finish_view():
            return
        await interaction.response.defer(ephemeral=True)
        if self._message is not None:
            try:
                await self._message.edit(view=self)
            except discord.HTTPException:
                pass
        await self._state.replay(interaction)

    async def on_timeout(self) -> None:
        if self._enable_task is not None and not self._enable_task.done():
            self._enable_task.cancel()
        self._finish_view()
        await self._delete_message(delay=5.0)
