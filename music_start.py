#!/usr/bin/env python3
"""Music Bot tmux Session Manager

Manages the Discord music bot in a detached tmux session with features:
- Auto-restart on crash (--respawn)
- Log file output (--log-file)
- Session lifecycle management (start/stop/restart/attach/status)
"""

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_SESSION = "music_bot"
DEFAULT_LOG_FILE = "logs/music_bot.log"  # Changed from None for better UX


def _default_cmd() -> str:
    """Determine the command to run the bot.

    Prefers the installed console script 'discord-music-player' if available,
    otherwise falls back to running src/discord_music_player/main.py with the current Python interpreter.

    Returns:
        Shell command string to execute the bot.
    """
    if shutil.which("discord-music-player"):
        return "discord-music-player"
    return f"{shlex.quote(sys.executable)} src/discord_music_player/main.py"


DEFAULT_CMD = _default_cmd()


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Execute a command and capture its output.

    Args:
        cmd: Command and arguments as a list.

    Returns:
        CompletedProcess with stdout/stderr as text.
    """
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def tmux_exists() -> bool:
    """Check if tmux is installed and available on PATH."""
    return shutil.which("tmux") is not None


def has_session(name: str) -> bool:
    """Check if a tmux session with the given name exists.

    Args:
        name: Session name to check.

    Returns:
        True if session exists, False otherwise.
    """
    res = run(["tmux", "has-session", "-t", name])
    return res.returncode == 0


def start_session(
    session: str,
    cmd: str,
    respawn: bool,
    log_file: str | None,
) -> None:
    """Start the bot in a detached tmux session.

    Args:
        session: Name of the tmux session.
        cmd: Command to run inside the session.
        respawn: If True, auto-restart the bot when it exits.
        log_file: Optional path to log file. If None, uses DEFAULT_LOG_FILE.
    """
    if has_session(session):
        print(f"[ok] tmux session '{session}' is already running.")
        print(f"    attach:  tmux attach -t {session}")
        return

    # Use default log file if not specified
    log_path_str = log_file or DEFAULT_LOG_FILE
    log_path = Path(log_path_str)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the command that runs inside tmux
    # Source .env if present, add node to PATH, then run the bot command
    # Try to find node in common locations
    node_cmd = shutil.which("node")
    if node_cmd:
        node_dir = Path(node_cmd).parent
        env_prelude = f"set -a; [ -f .env ] && . ./.env; set +a; export PATH={shlex.quote(str(node_dir))}:$PATH;"
    else:
        env_prelude = "set -a; [ -f .env ] && . ./.env; set +a;"

    # Always use tee for logging (makes debugging easier)
    inner_cmd = f"{env_prelude} {cmd} 2>&1 | tee -a {shlex.quote(str(log_path))}"

    if respawn:
        # Keep restarting the bot if it crashes
        inner_cmd = (
            f"while true; do "
            f"{inner_cmd}; "
            f'echo "[respawn] process exited with code $?" ; '
            f"sleep 2; "
            f"done"
        )

    # Launch detached tmux session
    repo_root = Path(__file__).resolve().parent
    res = run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session,
            "-c",
            str(repo_root),
            "bash",
            "-lc",
            inner_cmd,
        ]
    )

    if res.returncode != 0:
        error_msg = res.stderr.strip() or f"Failed to create tmux session '{session}'"
        print(f"[err] {error_msg}")
        sys.exit(1)

    # Wait for session to initialize
    time.sleep(2)

    # Verify session is actually running
    if not has_session(session):
        print(f"[err] tmux session '{session}' failed to start.")
        print(f"      Check logs for details: {log_path}")
        sys.exit(1)

    # Success - print helpful info
    print(f"[ok] Bot started in tmux session '{session}'")
    print(f"    attach:  tmux attach -t {session}")
    print(f"    logs:    tail -f {log_path}")
    print("    stop:    python music_start.py stop")


def stop_session(session: str) -> None:
    """Stop a running tmux session.

    Args:
        session: Name of the tmux session to stop.
    """
    if not has_session(session):
        print(f"[ok] tmux session '{session}' is not running.")
        return

    res = run(["tmux", "kill-session", "-t", session])
    if res.returncode != 0:
        error_msg = res.stderr.strip() or f"Failed to kill session '{session}'"
        print(f"[err] {error_msg}")
        sys.exit(1)

    print(f"[ok] Stopped tmux session '{session}'.")


def attach_session(session: str) -> None:
    """Attach to a running tmux session (replaces current process).

    Args:
        session: Name of the tmux session to attach to.
    """
    if not has_session(session):
        print(f"[err] Session '{session}' is not running.")
        print("      Start it with: python music_start.py start")
        sys.exit(1)

    # Replace current process with tmux attach
    os.execvp("tmux", ["tmux", "attach-session", "-t", session])


def status_session(session: str) -> None:
    """Display status of the tmux session.

    Args:
        session: Name of the tmux session to check.
    """
    if not has_session(session):
        print(f"[status] '{session}': NOT RUNNING")
        sys.exit(1)

    # Get session window information
    ls = run(
        [
            "tmux",
            "list-windows",
            "-t",
            session,
            "-F",
            "#{window_index}:#{window_name}:#{window_active}",
        ]
    )

    print(f"[status] '{session}': RUNNING")
    if ls.returncode == 0 and ls.stdout.strip():
        for line in ls.stdout.strip().splitlines():
            idx, name, active = line.split(":")
            active_marker = "*" if active == "1" else " "
            print(f"  {active_marker} window {idx}: {name}")
    else:
        print("  (no window information available)")


def ensure_tmux_or_die() -> None:
    """Exit with error if tmux is not installed."""
    if not tmux_exists():
        print("[err] tmux is not installed.")
        print("      Install with: apt install tmux  (or: brew install tmux)")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Manage the Discord music bot in a tmux session.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start              # Start the bot
  %(prog)s start --respawn    # Start with auto-restart on crash
  %(prog)s attach             # Attach to running session
  %(prog)s stop               # Stop the bot
  %(prog)s restart            # Restart the bot
  %(prog)s status             # Show session status
        """,
    )

    parser.add_argument(
        "--session",
        "-s",
        default=DEFAULT_SESSION,
        help=f"tmux session name (default: {DEFAULT_SESSION})",
    )
    parser.add_argument(
        "--cmd",
        "-c",
        default=DEFAULT_CMD,
        help=f"command to run (default: {DEFAULT_CMD})",
    )
    parser.add_argument(
        "--log-file",
        "-l",
        default=None,
        help=f"log file path (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--respawn",
        action="store_true",
        help="auto-restart the bot if it exits",
    )

    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("start", help="start the bot in tmux")
    subparsers.add_parser("stop", help="stop the bot")
    subparsers.add_parser("restart", help="restart the bot")
    subparsers.add_parser("attach", help="attach to the tmux session")
    subparsers.add_parser("status", help="show session status")

    return parser


def main() -> None:
    """Main entry point for the CLI."""
    args = build_parser().parse_args()
    ensure_tmux_or_die()

    # Normalize session name (tmux doesn't like spaces or special chars)
    session = args.session.strip().replace(" ", "_")
    cmd = args.cmd.strip()

    if args.action == "start":
        start_session(session, cmd, args.respawn, args.log_file)
    elif args.action == "stop":
        stop_session(session)
    elif args.action == "restart":
        stop_session(session)
        start_session(session, cmd, args.respawn, args.log_file)
    elif args.action == "attach":
        attach_session(session)
    elif args.action == "status":
        status_session(session)
    else:
        # Should never reach here due to required=True on subparsers
        print(f"[err] Unknown action: {args.action}")
        sys.exit(2)


if __name__ == "__main__":
    main()
