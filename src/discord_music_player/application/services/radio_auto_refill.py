"""Auto-refill subscriber for the radio feature.

When the queue is exhausted and radio is enabled, automatically
generates more recommendations and restarts playback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.shared.events import QueueExhausted, get_event_bus

if TYPE_CHECKING:
    from .playback_service import PlaybackApplicationService
    from .radio_service import RadioApplicationService

logger = logging.getLogger(__name__)


class RadioAutoRefill:
    """Subscribes to QueueExhausted and refills when radio is active."""

    def __init__(
        self,
        *,
        radio_service: RadioApplicationService,
        playback_service: PlaybackApplicationService,
    ) -> None:
        self._radio_service = radio_service
        self._playback_service = playback_service
        self._bus = get_event_bus()
        self._started = False

    def start(self) -> None:
        """Start listening to events."""
        if self._started:
            return
        self._bus.subscribe(QueueExhausted, self._on_queue_exhausted)
        self._started = True

    def stop(self) -> None:
        """Stop listening to events."""
        if not self._started:
            return
        self._bus.unsubscribe(QueueExhausted, self._on_queue_exhausted)
        self._started = False

    async def _on_queue_exhausted(self, event: QueueExhausted) -> None:
        if not self._radio_service.is_enabled(event.guild_id):
            return

        added = await self._radio_service.refill_queue(event.guild_id)
        if added > 0:
            await self._playback_service.start_playback(event.guild_id)
