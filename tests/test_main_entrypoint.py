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

import json
import logging
from unittest.mock import MagicMock, mock_open, patch

from pydantic import SecretStr

from discord_music_player.main import main, setup_logging


class TestLoggingSetup:
    """Tests for logging configuration."""

    def _make_valid_config(self) -> dict:
        return {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {},
            "loggers": {
                "aiosqlite": {"level": "WARNING"},
                "urllib3": {"level": "WARNING"},
                "httpx": {"level": "WARNING"},
            },
            "root": {"level": "INFO", "handlers": []},
        }

    def test_dictconfig_called_when_json_exists(self):
        """Should call dictConfig when logging_config.json exists."""
        config = self._make_valid_config()
        m = mock_open(read_data=json.dumps(config))
        with (
            patch("builtins.open", m),
            patch("logging.config.dictConfig") as mock_dc,
        ):
            setup_logging()

            mock_dc.assert_called_once_with(config)

    def test_fallback_to_basicconfig_when_json_missing(self):
        """Should fallback to basicConfig when logging_config.json is missing."""
        with (
            patch("builtins.open", side_effect=FileNotFoundError),
            patch("logging.basicConfig") as mock_bc,
        ):
            setup_logging()

            mock_bc.assert_called_once()
            assert mock_bc.call_args[1]["level"] == logging.INFO

    def test_fallback_to_basicconfig_when_json_malformed(self):
        """Should fallback to basicConfig when JSON is malformed."""
        m = mock_open(read_data="{invalid json")
        with (
            patch("builtins.open", m),
            patch("logging.basicConfig") as mock_bc,
        ):
            setup_logging()

            mock_bc.assert_called_once()

    def test_root_logger_level_overridden_by_settings(self):
        """Should override root logger level with the provided log_level."""
        config = self._make_valid_config()
        m = mock_open(read_data=json.dumps(config))
        with (
            patch("builtins.open", m),
            patch("logging.config.dictConfig"),
            patch("logging.getLogger") as mock_get_logger,
        ):
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root

            setup_logging("DEBUG")

            mock_root.setLevel.assert_called_once_with(logging.DEBUG)

    def test_noisy_library_loggers_suppressed_via_json(self):
        """Should suppress noisy library loggers via the JSON config."""
        config = self._make_valid_config()
        m = mock_open(read_data=json.dumps(config))
        with (
            patch("builtins.open", m),
            patch("logging.config.dictConfig") as mock_dc,
        ):
            setup_logging()

            loaded = mock_dc.call_args[0][0]
            for name in ("aiosqlite", "urllib3", "httpx"):
                assert loaded["loggers"][name]["level"] == "WARNING"


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
