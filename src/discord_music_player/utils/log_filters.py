"""Logging filters that tame third-party log noise."""

from __future__ import annotations

import logging

import aiohttp

_DISCORD_CLIENT_LOGGER = "discord.client"


class ReconnectNoiseFilter(logging.Filter):
    """Quiet discord.py's auto-reconnect log for transient network failures.

    discord.py's connect loop emits ``log.exception('Attempting a reconnect in
    %.2fs')`` for every recoverable disconnect, dumping a full traceback at ERROR
    even though the loop self-heals. For network-layer causes (DNS, refused
    connections, timeouts) this rewrites the record to a single WARNING line and
    drops the traceback; genuine errors keep their original ERROR + traceback.
    """

    _RECONNECT_MSG = "Attempting a reconnect in %.2fs"
    _TRANSIENT: tuple[type[BaseException], ...] = (OSError, TimeoutError, aiohttp.ClientError)
    _REWRITE = "Lost connection to Discord (%s); retrying in %.2fs"

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg != self._RECONNECT_MSG or record.exc_info is None:
            return True

        exc = record.exc_info[1]
        if not isinstance(exc, self._TRANSIENT):
            return True

        retry = record.args[0] if record.args else 0.0
        record.levelno = logging.WARNING
        record.levelname = logging.getLevelName(logging.WARNING)
        record.exc_info = None
        record.exc_text = None
        record.msg = self._REWRITE
        record.args = (type(exc).__name__, retry)
        return True


def install_reconnect_filter() -> None:
    """Attach :class:`ReconnectNoiseFilter` to the ``discord.client`` logger once."""
    logger = logging.getLogger(_DISCORD_CLIENT_LOGGER)
    if not any(isinstance(f, ReconnectNoiseFilter) for f in logger.filters):
        logger.addFilter(ReconnectNoiseFilter())
