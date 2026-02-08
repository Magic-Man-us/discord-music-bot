"""
Tests for music_start.py tmux session management script.

Tests for the tmux session manager that handles starting, stopping,
restarting, attaching to, and checking status of the Discord bot
running in a tmux session.
"""

from unittest.mock import MagicMock, patch

import pytest

import music_start


class TestUtilityFunctions:
    """Tests for utility helper functions."""

    def test_default_cmd_with_installed_script(self):
        """Should use installed console script if available."""
        with patch("shutil.which", return_value="/usr/local/bin/discord-music-player"):
            result = music_start._default_cmd()

        assert result == "discord-music-player"

    def test_default_cmd_fallback_to_main_py(self):
        """Should fallback to src/discord_music_player/main.py with current Python if script not installed."""
        with patch("shutil.which", return_value=None):
            result = music_start._default_cmd()

        assert "src/discord_music_player/main.py" in result
        assert "python" in result.lower()

    def test_tmux_exists_when_available(self):
        """Should return True when tmux is available."""
        with patch("shutil.which", return_value="/usr/bin/tmux"):
            assert music_start.tmux_exists() is True

    def test_tmux_exists_when_not_available(self):
        """Should return False when tmux is not available."""
        with patch("shutil.which", return_value=None):
            assert music_start.tmux_exists() is False


class TestSessionManagement:
    """Tests for tmux session management functions."""

    def test_has_session_returns_true(self):
        """Should return True when session exists."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch.object(music_start, "run", return_value=mock_result):
            result = music_start.has_session("test_session")

        assert result is True

    def test_has_session_returns_false(self):
        """Should return False when session doesn't exist."""
        mock_result = MagicMock()
        mock_result.returncode = 1

        with patch.object(music_start, "run", return_value=mock_result):
            result = music_start.has_session("test_session")

        assert result is False

    def test_start_session_skips_if_already_running(self, capsys):
        """Should skip starting if session already exists."""
        with patch.object(music_start, "has_session", return_value=True):
            music_start.start_session("test_session", "test_cmd", False, None)

        captured = capsys.readouterr()
        assert "already running" in captured.out

    def test_start_session_creates_new_session(self):
        """Should create new tmux session when not running."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", side_effect=[False, True]),
            patch.object(music_start, "run", return_value=mock_result) as mock_run,
            patch("time.sleep"),
        ):
            music_start.start_session("test_session", "test_cmd", False, None)

            # Verify tee is always used (with default log file when None provided)
            call_args = mock_run.call_args[0][0]
            cmd_str = " ".join(call_args)
            assert "tee" in cmd_str
            assert music_start.DEFAULT_LOG_FILE in cmd_str

    def test_start_session_with_respawn(self):
        """Should create session with respawn wrapper when respawn=True."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", side_effect=[False, True]),
            patch.object(music_start, "run", return_value=mock_result) as mock_run,
            patch("time.sleep"),
        ):
            music_start.start_session("test_session", "test_cmd", True, None)

            # Check that respawn wrapper is in the command
            call_args = mock_run.call_args[0][0]
            cmd_str = " ".join(call_args)
            assert "while true" in cmd_str
            assert "process exited with code" in cmd_str
            assert "sleep 2" in cmd_str

    def test_start_session_with_log_file(self):
        """Should configure tee logging when log file provided."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", side_effect=[False, True]),
            patch.object(music_start, "run", return_value=mock_result) as mock_run,
            patch("time.sleep"),
        ):
            music_start.start_session("test_session", "test_cmd", False, "logs/bot.log")

            # Check that tee is in the command with the specified log file
            call_args = mock_run.call_args[0][0]
            cmd_str = " ".join(call_args)
            assert "tee" in cmd_str
            assert "logs/bot.log" in cmd_str

    def test_start_session_uses_default_log_file(self):
        """Should use DEFAULT_LOG_FILE when log_file is None."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", side_effect=[False, True]),
            patch.object(music_start, "run", return_value=mock_result) as mock_run,
            patch("time.sleep"),
        ):
            music_start.start_session("test_session", "test_cmd", False, None)

            # Check that default log file is used
            call_args = mock_run.call_args[0][0]
            cmd_str = " ".join(call_args)
            assert music_start.DEFAULT_LOG_FILE in cmd_str

    def test_start_session_exits_on_failure(self):
        """Should exit with error if tmux session creation fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "tmux error"

        with (
            patch.object(music_start, "has_session", return_value=False),
            patch.object(music_start, "run", return_value=mock_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.start_session("test_session", "test_cmd", False, None)

        assert exc_info.value.code == 1

    def test_stop_session_when_not_running(self, capsys):
        """Should skip stopping if session not running."""
        with patch.object(music_start, "has_session", return_value=False):
            music_start.stop_session("test_session")

        captured = capsys.readouterr()
        assert "not running" in captured.out

    def test_stop_session_kills_existing_session(self):
        """Should kill existing tmux session."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", return_value=True),
            patch.object(music_start, "run", return_value=mock_result) as mock_run,
        ):
            music_start.stop_session("test_session")

            # Verify tmux kill-session was called
            call_args = mock_run.call_args[0][0]
            assert "kill-session" in call_args

    def test_attach_session_exits_if_not_running(self, capsys):
        """Should exit with error if session not running."""
        with (
            patch.object(music_start, "has_session", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.attach_session("test_session")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "is not running" in captured.out
        assert "Start it with:" in captured.out

    def test_attach_session_replaces_process(self):
        """Should replace current process with tmux attach."""
        with (
            patch.object(music_start, "has_session", return_value=True),
            patch("os.execvp") as mock_exec,
        ):
            music_start.attach_session("test_session")

            # Verify execvp was called with correct args
            mock_exec.assert_called_once()
            assert mock_exec.call_args[0][0] == "tmux"

    def test_status_session_exits_if_not_running(self, capsys):
        """Should exit with error if session not running."""
        with (
            patch.object(music_start, "has_session", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.status_session("test_session")

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "NOT RUNNING" in captured.out

    def test_status_session_shows_windows(self, capsys):
        """Should show windows when session is running."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0:bash:1\n1:vim:0\n"

        with (
            patch.object(music_start, "has_session", return_value=True),
            patch.object(music_start, "run", return_value=mock_result),
        ):
            music_start.status_session("test_session")

        captured = capsys.readouterr()
        assert "RUNNING" in captured.out
        assert "window 0: bash" in captured.out
        assert "window 1: vim" in captured.out
        assert "*" in captured.out  # Active window marker

    def test_status_session_shows_active_marker(self, capsys):
        """Should mark active window with asterisk."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0:bash:0\n1:vim:1\n"

        with (
            patch.object(music_start, "has_session", return_value=True),
            patch.object(music_start, "run", return_value=mock_result),
        ):
            music_start.status_session("test_session")

        captured = capsys.readouterr()
        lines = captured.out.strip().splitlines()
        # Window 0 should not have asterisk, window 1 should
        assert any("* window 1: vim" in line for line in lines)

    def test_status_session_handles_no_windows(self, capsys):
        """Should handle case when no window info is available."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch.object(music_start, "has_session", return_value=True),
            patch.object(music_start, "run", return_value=mock_result),
        ):
            music_start.status_session("test_session")

        captured = capsys.readouterr()
        assert "no window information available" in captured.out


class TestEnsureTmux:
    """Tests for tmux availability check."""

    def test_ensure_tmux_or_die_with_tmux(self):
        """Should pass when tmux is available."""
        with patch.object(music_start, "tmux_exists", return_value=True):
            music_start.ensure_tmux_or_die()  # Should not raise

    def test_ensure_tmux_or_die_without_tmux(self):
        """Should exit when tmux is not available."""
        with (
            patch.object(music_start, "tmux_exists", return_value=False),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.ensure_tmux_or_die()

        assert exc_info.value.code == 1


class TestArgumentParser:
    """Tests for argument parser configuration."""

    def test_build_parser_creates_parser(self):
        """Should create argument parser with all subcommands."""
        parser = music_start.build_parser()

        assert parser is not None
        # Check that default arguments exist
        args = parser.parse_args(["start"])
        assert hasattr(args, "session")
        assert hasattr(args, "cmd")
        assert hasattr(args, "action")

    def test_parser_requires_action(self):
        """Should require an action subcommand."""
        parser = music_start.build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args([])  # No action provided

    def test_parser_has_epilog_with_examples(self):
        """Should include epilog with usage examples."""
        parser = music_start.build_parser()

        assert parser.epilog is not None
        assert "Examples:" in parser.epilog
        assert "start" in parser.epilog
        assert "--respawn" in parser.epilog

    def test_parser_all_actions_available(self):
        """Should have all expected actions as subcommands."""
        parser = music_start.build_parser()

        # Test each action can be parsed
        for action in ["start", "stop", "restart", "attach", "status"]:
            args = parser.parse_args([action])
            assert args.action == action


class TestSessionEdgeCases:
    """Tests for edge cases in session management."""

    def test_start_session_validation_failure(self):
        """Should exit if session fails to start after creation."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        # First call: session doesn't exist
        # Second call (after sleep): session still doesn't exist (failed to start)
        with (
            patch.object(music_start, "has_session", side_effect=[False, False]),
            patch.object(music_start, "run", return_value=mock_result),
            patch("time.sleep"),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.start_session("test_session", "test_cmd", False, None)

        assert exc_info.value.code == 1

    def test_stop_session_handles_failure(self):
        """Should exit with error when kill-session fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Permission denied"

        with (
            patch.object(music_start, "has_session", return_value=True),
            patch.object(music_start, "run", return_value=mock_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            music_start.stop_session("test_session")

        assert exc_info.value.code == 1

    def test_start_session_helpful_output_on_success(self, capsys):
        """Should print helpful commands when session starts successfully."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(music_start, "has_session", side_effect=[False, True]),
            patch.object(music_start, "run", return_value=mock_result),
            patch("time.sleep"),
        ):
            music_start.start_session("test_session", "test_cmd", False, None)

        captured = capsys.readouterr()
        assert "attach:" in captured.out
        assert "logs:" in captured.out
        assert "stop:" in captured.out
        assert "tmux attach -t test_session" in captured.out


class TestMainFunction:
    """Tests for main entry point."""

    def test_main_start_action(self):
        """Should call start_session for start action."""
        test_args = ["--session", "test", "start"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()
            mock_start.assert_called_once()

    def test_main_stop_action(self):
        """Should call stop_session for stop action."""
        test_args = ["--session", "test", "stop"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "stop_session") as mock_stop,
        ):
            music_start.main()
            mock_stop.assert_called_once()

    def test_main_restart_action(self):
        """Should call stop then start for restart action."""
        test_args = ["--session", "test", "restart"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "stop_session") as mock_stop,
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()
            mock_stop.assert_called_once()
            mock_start.assert_called_once()

    def test_main_normalizes_session_name(self):
        """Should normalize session name (remove spaces)."""
        test_args = ["--session", "my session", "start"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()

            # Check that session name had spaces replaced with underscores
            called_session = mock_start.call_args[0][0]
            assert " " not in called_session
            assert "_" in called_session

    def test_main_attach_action(self):
        """Should call attach_session for attach action."""
        test_args = ["--session", "test", "attach"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "attach_session") as mock_attach,
        ):
            music_start.main()
            mock_attach.assert_called_once()

    def test_main_status_action(self):
        """Should call status_session for status action."""
        test_args = ["--session", "test", "status"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "status_session") as mock_status,
        ):
            music_start.main()
            mock_status.assert_called_once()

    def test_main_with_custom_log_file(self):
        """Should pass custom log file to start_session."""
        test_args = ["--session", "test", "--log-file", "custom.log", "start"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()

            # Check that custom log file was passed
            assert mock_start.call_args[0][3] == "custom.log"

    def test_main_with_respawn_flag(self):
        """Should pass respawn flag to start_session."""
        test_args = ["--session", "test", "--respawn", "start"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()

            # Check that respawn=True was passed
            assert mock_start.call_args[0][2] is True

    def test_main_with_custom_cmd(self):
        """Should pass custom command to start_session."""
        test_args = ["--session", "test", "--cmd", "custom-command", "start"]

        with (
            patch("sys.argv", ["music_start.py"] + test_args),
            patch.object(music_start, "ensure_tmux_or_die"),
            patch.object(music_start, "start_session") as mock_start,
        ):
            music_start.main()

            # Check that custom command was passed
            assert mock_start.call_args[0][1] == "custom-command"
