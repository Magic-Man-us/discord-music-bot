#!/usr/bin/env python3
"""Main entry point for the Discord Music Bot."""

from __future__ import annotations

import logging
import sys

from discord_music_player.domain.shared.messages import ErrorMessages, LogTemplates


def setup_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


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


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
