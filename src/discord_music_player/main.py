#!/usr/bin/env python3
"""Main entry point for the Discord Music Bot."""

from __future__ import annotations

import json
import logging
import logging.config
import sys
from pathlib import Path

from discord_music_player.domain.shared.messages import ErrorMessages, LogTemplates

_LOGGING_CONFIG_PATH = Path(__file__).resolve().parents[2] / "logging_config.json"


def setup_logging(log_level: str = "INFO") -> None:
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)

    try:
        with open(_LOGGING_CONFIG_PATH) as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        logging.warning(
            "Could not load %s, falling back to basic config", _LOGGING_CONFIG_PATH
        )
        logging.basicConfig(
            level=resolved_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    logging.getLogger().setLevel(resolved_level)


def main() -> int:
    from discord_music_player.config.settings import get_settings

    settings = get_settings()
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)

    token_value = settings.discord.token.get_secret_value()
    if not token_value:
        logger.error(ErrorMessages.DISCORD_TOKEN_REQUIRED)
        return 1

    logger.info(LogTemplates.BOT_STARTING.format(environment=settings.environment))

    from discord_music_player.config.container import create_container
    from discord_music_player.infrastructure.discord.bot import create_bot

    container = create_container(settings)
    bot = create_bot(container, settings)

    try:
        logger.info(LogTemplates.BOT_STARTING_RUN)
        bot.run_with_graceful_shutdown(token_value)
        logger.info(LogTemplates.BOT_STOPPED)
        return 0
    except KeyboardInterrupt:
        logger.info(LogTemplates.BOT_KEYBOARD_INTERRUPT)
        return 0
    except Exception as e:
        logger.exception(LogTemplates.BOT_FATAL_ERROR, e)
        return 1


def cli() -> None:
    """Console script entry point (used by pyproject.toml [project.scripts])."""
    sys.exit(main())


if __name__ == "__main__":
    cli()  # pragma: no cover
