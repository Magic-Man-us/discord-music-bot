#!/usr/bin/env python3
"""Main entry point for the Discord Music Bot."""

from __future__ import annotations

import fcntl
import json
import logging
import logging.config
import os
import sys
from pathlib import Path

from .utils.logging import get_logger

_LOGGING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "logging_config.json"
_PID_FILE = Path(__file__).resolve().parents[2] / "bot.pid"


def setup_logging(log_level: str = "INFO") -> None:
    resolved_level = logging.getLevelNamesMapping().get(log_level.upper(), logging.INFO)

    try:
        with open(_LOGGING_CONFIG_PATH) as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    except (
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
        KeyError,
        ImportError,
        AttributeError,
    ):
        logging.warning("Could not load %s, falling back to basic config", _LOGGING_CONFIG_PATH)
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Apply runtime log level to root and all application loggers
    logging.getLogger().setLevel(resolved_level)
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("discord_music_player"):
            logging.getLogger(name).setLevel(resolved_level)


def _acquire_pid_lock(logger: logging.Logger) -> int | None:
    """Acquire an exclusive lock via bot.pid. Returns the fd or None on failure."""
    try:
        fd = _PID_FILE.open("w")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd  # type: ignore[return-value]  # keep fd alive to hold lock
    except OSError:
        try:
            existing_pid = _PID_FILE.read_text().strip()
        except OSError:
            existing_pid = "unknown"
        logger.error("Another bot instance is already running (PID %s). Exiting.", existing_pid)
        return None


def main() -> int:
    from .config.settings import get_settings

    settings = get_settings()
    setup_logging(settings.log_level)

    logger = get_logger(__name__)

    lock = _acquire_pid_lock(logger)
    if lock is None:
        return 1

    try:
        token_value = settings.discord.token.get_secret_value()
        if not token_value:
            logger.error("DISCORD_TOKEN environment variable is required")
            return 1

        logger.info("Starting Discord Music Bot in %s mode", settings.environment)

        from .config.container import create_container
        from .infrastructure.discord.bot import create_bot

        container = create_container(settings)
        bot = create_bot(container, settings)

        logger.info("Starting bot...")
        bot.run_with_graceful_shutdown(token_value)
        logger.info("Bot stopped successfully")
        return 0
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
        return 0
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1
    finally:
        try:
            lock.close()  # type: ignore[union-attr]
            _PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def cli() -> None:
    """Console script entry point (used by pyproject.toml [project.scripts])."""
    sys.exit(main())


if __name__ == "__main__":
    cli()  # pragma: no cover
