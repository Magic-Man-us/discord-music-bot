# Development

## Makefile Commands

Run `make help` to see all available targets. Below is the full reference:

### Setup

| Command | Description |
|---------|-------------|
| `make setup` | Full first-time setup: checks prereqs, creates `.venv`, installs deps, creates `.env`, starts POT provider |
| `make prereqs` | Check that Python 3.12+, ffmpeg, Docker, and docker-compose are installed |
| `make install` | Install production dependencies (`pip install -e .`) |
| `make dev` | Install with dev and test dependencies (`pip install -e ".[dev,test]"`) |
| `make setup-env` | Create `.env` from `.env.example` (skips if `.env` exists) |

### Quality

| Command | Description |
|---------|-------------|
| `make test` | Run tests with pytest |
| `make test-cov` | Run tests with coverage report (HTML output in `htmlcov/`) |
| `make lint` | Lint with ruff |
| `make format` | Auto-format code with ruff |
| `make check` | Run lint + tests together |

### Running

| Command | Description |
|---------|-------------|
| `make run` | Run the bot directly (requires `.env` file) |
| `make run-tmux` | Run the bot in tmux with auto-respawn (uses `music_start.py`) |

### Database

| Command | Description |
|---------|-------------|
| `make db-reset` | Delete the SQLite database files (interactive confirmation) |

### YouTube POT Provider

The POT (Proof of Origin Token) provider is a Docker container that generates tokens to prevent YouTube 403 errors. It must be running for YouTube playback to work reliably.

| Command | Description |
|---------|-------------|
| `make pot-start` | Start the bgutil POT provider container |
| `make pot-stop` | Stop the POT provider container |
| `make pot-logs` | Tail the POT provider logs |
| `make pot-status` | Check if the POT provider is running |

### Utilities

| Command | Description |
|---------|-------------|
| `make clean` | Remove `__pycache__`, `.egg-info`, `.pytest_cache`, `.ruff_cache`, coverage files |
| `make info` | Show Python version and installed dependency versions |
| `make help` | Show all available make targets |

## Project Structure

```
src/discord_music_player/
  domain/             # Business logic (entities, value objects, services)
  application/        # Use cases (commands, queries, services)
  infrastructure/     # External adapters (Discord, yt-dlp, FFmpeg, SQLite, AI via pydantic-ai)
  config/             # Settings and dependency injection container
```

## Architecture Patterns

### Callback Pattern

Application services notify the infrastructure layer (Discord cogs) via registered callbacks. This keeps the application layer free of Discord dependencies.

- **Track finished**: `PlaybackApplicationService.set_track_finished_callback` notifies `MusicCog._on_track_finished` to update Discord messages (transition now-playing to finished, promote queued to now-playing).
- **Requester left**: `AutoSkipOnRequesterLeave.set_on_requester_left_callback` notifies `MusicCog._on_requester_left` to send a confirmation view with Yes/No buttons.

### Event Bus

Domain events are published via a singleton `EventBus` (subscribe/publish pattern). Voice state changes (member joined/left) are published by `EventCog` and consumed by application services like `AutoSkipOnRequesterLeave`.

### Requester Leave Flow

When the user who requested the currently playing track leaves the voice channel:

1. Bot **pauses** playback
2. Bot sends a prompt with **Yes** / **No** buttons to the text channel
3. **Yes** resumes playback, **No** skips, **30s timeout** auto-skips
4. If no listeners remain in the channel, the track is skipped immediately without prompting
