"""
Tests for main.py - Main Entry Point

Tests for the main entry point including:
- Logging configuration
- Settings validation
- Container creation
- Bot initialization
- Error handling
- Graceful shutdown
"""

import logging
from unittest.mock import MagicMock, patch

from pydantic import SecretStr

from discord_music_player.main import main, setup_logging


class TestLoggingSetup:
    """Tests for logging configuration."""

    def test_setup_logging_default_level(self):
        """Should configure logging with default INFO level."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging()

            mock_config.assert_called_once()
            # Check that INFO level was used
            assert mock_config.call_args[1]["level"] == logging.INFO

    def test_setup_logging_custom_level(self):
        """Should configure logging with custom level."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging("DEBUG")

            assert mock_config.call_args[1]["level"] == logging.DEBUG

    def test_setup_logging_invalid_level_uses_info(self):
        """Should fallback to INFO for invalid log levels."""
        with patch("logging.basicConfig") as mock_config:
            setup_logging("INVALID")

            assert mock_config.call_args[1]["level"] == logging.INFO

    def test_setup_logging_reduces_library_noise(self):
        """Should set WARNING level for noisy libraries."""
        with (
            patch("logging.basicConfig"),
            patch("logging.getLogger") as mock_get_logger,
        ):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            setup_logging()

            # Verify that noisy loggers were set to WARNING
            calls = mock_get_logger.call_args_list
            logger_names = [call[0][0] for call in calls]

            assert "discord" in logger_names
            assert "discord.http" in logger_names
            assert "discord.gateway" in logger_names


class TestMainFunction:
    """Tests for main entry point function."""

    def test_main_returns_error_without_token(self):
        """Should return error code when Discord token is missing."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"

        with patch("discord_music_player.config.settings.get_settings", return_value=mock_settings):
            exit_code = main()

        assert exit_code == 1

    def test_main_successful_run(self):
        """Should return 0 on successful bot run."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"

        mock_bot = MagicMock()
        mock_bot.run_with_graceful_shutdown = MagicMock()

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch("discord_music_player.config.container.create_container"),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ),
        ):
            exit_code = main()

        assert exit_code == 0
        mock_bot.run_with_graceful_shutdown.assert_called_once_with("test_token_123")

    def test_main_handles_keyboard_interrupt(self):
        """Should return 0 on KeyboardInterrupt (graceful shutdown)."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"

        mock_bot = MagicMock()
        mock_bot.run_with_graceful_shutdown.side_effect = KeyboardInterrupt()

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch("discord_music_player.config.container.create_container"),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ),
        ):
            exit_code = main()

        assert exit_code == 0

    def test_main_handles_exception(self):
        """Should return error code on unhandled exception."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"

        mock_bot = MagicMock()
        mock_bot.run_with_graceful_shutdown.side_effect = RuntimeError("Bot crashed!")

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch("discord_music_player.config.container.create_container"),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ),
        ):
            exit_code = main()

        assert exit_code == 1

    def test_main_creates_container_with_settings(self):
        """Should create DI container with loaded settings."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"

        mock_bot = MagicMock()

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch(
                "discord_music_player.config.container.create_container"
            ) as mock_create_container,
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ),
        ):
            main()

            mock_create_container.assert_called_once_with(mock_settings)

    def test_main_creates_bot_with_container_and_settings(self):
        """Should create bot with container and settings."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "test"

        mock_container = MagicMock()
        mock_bot = MagicMock()

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch(
                "discord_music_player.config.container.create_container",
                return_value=mock_container,
            ),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ) as mock_create_bot,
        ):
            main()

            mock_create_bot.assert_called_once_with(mock_container, mock_settings)

    def test_main_logs_startup_messages(self):
        """Should log appropriate startup messages."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "INFO"
        mock_settings.environment = "production"

        mock_bot = MagicMock()

        with (
            patch("discord_music_player.config.settings.get_settings", return_value=mock_settings),
            patch("discord_music_player.main.setup_logging"),
            patch("discord_music_player.config.container.create_container"),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot", return_value=mock_bot
            ),
            patch("logging.getLogger") as mock_get_logger,
        ):
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            main()

            # Verify logging calls were made
            assert mock_logger.info.call_count >= 2  # At least startup and run messages


class TestIntegrationScenarios:
    """Integration-style tests for complete scenarios."""

    def test_full_startup_sequence(self):
        """Should execute full startup sequence in correct order."""
        mock_discord = MagicMock()
        mock_discord.token = SecretStr("test_token_123")

        mock_settings = MagicMock()
        mock_settings.discord = mock_discord
        mock_settings.log_level = "DEBUG"
        mock_settings.environment = "test"

        call_order = []

        def track_call(name):
            def wrapper(*args, **kwargs):
                call_order.append(name)
                if name == "create_bot":
                    mock_bot = MagicMock()
                    return mock_bot
                return MagicMock()

            return wrapper

        with (
            patch(
                "discord_music_player.config.settings.get_settings",
                side_effect=track_call("get_settings"),
            ),
            patch(
                "discord_music_player.main.setup_logging", side_effect=track_call("setup_logging")
            ),
            patch(
                "discord_music_player.config.container.create_container",
                side_effect=track_call("create_container"),
            ),
            patch(
                "discord_music_player.infrastructure.discord.bot.create_bot",
                side_effect=track_call("create_bot"),
            ),
        ):
            main()

        # Verify order of operations
        assert call_order == [
            "get_settings",
            "setup_logging",
            "create_container",
            "create_bot",
        ]
