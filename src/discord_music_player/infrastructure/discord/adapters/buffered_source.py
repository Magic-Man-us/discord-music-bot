"""Prebuffering AudioSource wrapper for discord.py playback."""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Final

import discord

from ....domain.shared.constants import AudioConstants
from ....utils.logging import get_logger

if TYPE_CHECKING:
    from ....config.settings import PrebufferSettings

logger = get_logger(__name__)

_EOF: Final[bytes] = b""
_SILENCE: Final[bytes] = b"\x00" * AudioConstants.PCM_FRAME_BYTES

# A frame is due every 20 ms. Waiting much past that on an already-empty buffer only
# pushes the send loop further behind, so give up quickly and emit silence instead.
_FRAME_WAIT_SECONDS: Final[float] = 0.05
_PUT_WAIT_SECONDS: Final[float] = 0.5


class BufferedAudioSource(discord.AudioSource):
    """Reads the wrapped source on a background thread so an upstream network stall
    drains the prebuffer instead of starving discord.py's 20 ms send loop.

    Subclasses discord.AudioSource because discord.py drives read/is_opus/cleanup by
    that contract; the tuning knobs live in the PrebufferSettings model.
    """

    def __init__(self, source: discord.AudioSource, config: PrebufferSettings) -> None:
        self._source = source
        self._config = config
        self._frames: queue.Queue[bytes] = queue.Queue(maxsize=config.buffer_frames)
        self._stopped = threading.Event()
        self._primed = threading.Event()
        self._underruns = 0
        self._reader = threading.Thread(
            target=self._fill,
            name=f"audio-prebuffer:{id(self):#x}",
            daemon=True,
        )
        self._reader.start()

    def _fill(self) -> None:
        try:
            while not self._stopped.is_set():
                data = self._source.read()
                if not self._offer(data):
                    return
                if (
                    not self._primed.is_set()
                    and self._frames.qsize() >= self._config.prefill_frames
                ):
                    self._primed.set()
                if data == _EOF:
                    return
        except Exception:
            logger.exception("Prebuffer reader failed; ending playback")
            self._offer(_EOF)
        finally:
            # Unblock read() whether we filled, hit EOF, or died.
            self._primed.set()

    def _offer(self, data: bytes) -> bool:
        """Park a frame in the buffer. A full buffer backpressures FFmpeg the same way
        the raw pipe did. Returns False once the source has been stopped."""
        while not self._stopped.is_set():
            try:
                self._frames.put(data, timeout=_PUT_WAIT_SECONDS)
            except queue.Full:
                continue
            return True
        return False

    def read(self) -> bytes:
        self._primed.wait(timeout=self._config.prefill_timeout)
        try:
            return self._frames.get(timeout=_FRAME_WAIT_SECONDS)
        except queue.Empty:
            if not self._reader.is_alive():
                return _EOF
            self._underruns += 1
            logger.warning(
                "Audio prebuffer underrun (%d so far); emitting silence", self._underruns
            )
            return _SILENCE

    def is_opus(self) -> bool:
        return self._source.is_opus()

    def cleanup(self) -> None:
        self._stopped.set()
        self._primed.set()
        self._reader.join(timeout=_PUT_WAIT_SECONDS)
        self._source.cleanup()
