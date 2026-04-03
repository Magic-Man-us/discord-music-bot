"""Auto-refill subscriber: replenishes radio queue from the recommendation pool."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.shared.events import QueueExhausted, TrackStartedPlaying, get_event_bus
from ...utils.logging import get_logger

if TYPE_CHECKING:
    from .playback_service import PlaybackApplicationService
    from .radio_service import RadioApplicationService

logger = get_logger(__name__)


class RadioAutoRefill:
    """Subscribes to playback events and replenishes from the radio pool.

    - QueueExhausted: refill the queue from the pool so playback continues.
    - TrackStartedPlaying: pre-fetch one track from the pool when the queue
      is empty behind the currently playing track.
    """

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
        if self._started:
            return
        self._bus.subscribe(QueueExhausted, self._on_queue_exhausted)
        self._bus.subscribe(TrackStartedPlaying, self._on_track_started)
        self._started = True

    def stop(self) -> None:
        if not self._started:
            return
        self._bus.unsubscribe(QueueExhausted, self._on_queue_exhausted)
        self._bus.unsubscribe(TrackStartedPlaying, self._on_track_started)
        self._started = False

    async def _on_queue_exhausted(self, event: QueueExhausted) -> None:
        if not self._radio_service.is_enabled(event.guild_id):
            return

        added = await self._radio_service.refill_queue(event.guild_id)
        if added > 0:
            await self._playback_service.start_playback(event.guild_id)

    async def _on_track_started(self, event: TrackStartedPlaying) -> None:
        """Pre-fetch one track from the pool when the queue is empty."""
        guild_id = event.guild_id
        if not self._radio_service.is_enabled(guild_id):
            return

        if await self._radio_service.has_queued_tracks(guild_id):
            return

        try:
            await self._radio_service.replenish_from_pool(guild_id)
        except Exception:
            logger.exception("Radio pool replenish failed for guild %s", guild_id)
