#!/usr/bin/env python3
"""
Discord Music Bot - Main Entry Point

Main entry point for the Discord Music Bot using Domain-Driven Design architecture.
"""

from __future__ import annotations

import logging
import sys

from discord_music_player.domain.shared.messages import ErrorMessages, LogTemplates


def setup_logging(log_level: str = "INFO") -> None:
    """Configure application logging with structured format and library filtering.

    Sets up the root logger with a consistent format including timestamp, level,
    and module name. Also configures third-party libraries (discord.py, aiosqlite,
    httpx) to use WARNING level to reduce log noise.

    Args:
        log_level: The logging level to use (e.g., "INFO", "DEBUG", "WARNING").
                   Defaults to "INFO".
    """
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Reduce noise from libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    """Main entry point for the Discord Music Bot.

    This function orchestrates the application startup sequence:
    1. Loads settings from environment variables
    2. Configures logging based on settings
    3. Validates required configuration (Discord token)
    4. Creates the dependency injection container
    5. Initializes and runs the bot with graceful shutdown handling

    The bot runs until interrupted or an error occurs. Signal handlers
    (SIGINT, SIGTERM) are configured for graceful shutdown.

    Returns:
        Exit code: 0 for successful shutdown, 1 for errors.
    """
    # Import settings
    from discord_music_player.config.settings import get_settings

    # Load settings from environment
    settings = get_settings()

    # Set up logging
    setup_logging(settings.log_level)

    logger = logging.getLogger(__name__)

    # Validate required settings
    token_value = settings.discord.token.get_secret_value()
    if not token_value:
        logger.error(ErrorMessages.DISCORD_TOKEN_REQUIRED)
        return 1

    logger.info(LogTemplates.BOT_STARTING.format(environment=settings.environment))

    # Create DI container and bot
    from discord_music_player.config.container import create_container
    from discord_music_player.infrastructure.discord.bot import create_bot

    # Create container
    container = create_container(settings)

    # Create and run bot
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
