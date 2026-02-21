"""Auto-refill subscriber that generates more radio tracks when the queue is exhausted."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...domain.shared.events import QueueExhausted, TrackStartedPlaying, get_event_bus

if TYPE_CHECKING:
    from .playback_service import PlaybackApplicationService
    from .radio_service import RadioApplicationService

logger = logging.getLogger(__name__)

WARMUP_RECENT_HISTORY = 10


class RadioAutoRefill:
    """Subscribes to QueueExhausted and refills when radio is active.

    Also pre-fetches a single track when the queue runs dry behind the
    currently playing track, so there is always one song waiting.
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
        """Pre-fetch one track when the queue is empty behind the current song."""
        guild_id = event.guild_id
        if not self._radio_service.is_enabled(guild_id):
            return

        session = await self._radio_service._session_repo.get(guild_id)
        if session is None or session.queue_length > 0:
            return

        try:
            await self._radio_service.warmup_next(
                guild_id, recent_limit=WARMUP_RECENT_HISTORY
            )
        except Exception:
            logger.exception("Radio warmup failed for guild %s", guild_id)
