# Discord Music Bot

A Discord music bot with AI-powered radio, built with clean architecture. Plays music from YouTube and other platforms using `yt-dlp` and `ffmpeg`, with features like queue management, vote skipping, and AI-driven song recommendations.

## Features

- **Music Playback** - Stream from YouTube, SoundCloud, and other platforms via URL or search
- **Queue Management** - Add, remove, shuffle, reorder, and loop tracks
- **AI Radio** - `/radio` auto-queues similar songs using OpenAI recommendations
- **Vote Skip** - Democratic skip voting with configurable thresholds
- **Auto-Skip** - Skips tracks when the requester leaves the voice channel
- **Slash Commands** - Modern Discord slash commands with rich embeds
- **Persistent State** - SQLite-backed queue, history, and session persistence
- **Health Monitoring** - Built-in health checks, uptime tracking, and statistics

## Prerequisites

- **Python 3.12+**
- **FFmpeg** - [ffmpeg.org](https://ffmpeg.org/)
- **Docker** and **Docker Compose** - For the YouTube POT provider ([Install Docker](https://docs.docker.com/get-docker/))
- **Discord Bot Token** - [Developer Portal](https://discord.com/developers/applications) with Message Content and Server Members intents enabled
- **tmux** *(optional)* - Only needed for `make run-tmux` / `music_start.py`

### System packages (Linux)

PyNaCl (required by discord.py for voice) ships pre-built wheels for most platforms. If pip fails to install it, you may need the build dependencies:

```bash
# Debian / Ubuntu
sudo apt install libffi-dev libsodium-dev python3-dev ffmpeg

# Fedora / RHEL
sudo dnf install libffi-devel libsodium-devel python3-devel ffmpeg

# macOS (Homebrew) — wheels usually just work, but if needed:
brew install libffi libsodium ffmpeg
```

Run `make prereqs` to verify all required tools are installed.

## Quick Start

```bash
# Clone and set up everything
git clone https://github.com/Magic-Man-us/discord-music-bot.git
cd discord-music-bot
make setup

# Edit .env with your Discord token and settings
# Then run the bot
make run
```

`make setup` checks prerequisites, creates a virtual environment, installs dependencies, generates `.env` from the example, and starts the YouTube POT provider. The database is created automatically on first run.

## Configuration

Copy `.env.example` to `.env` and edit it:

```bash
make setup-env   # creates .env from .env.example
```

All settings use Pydantic nested delimiter format (`SECTION__KEY=value`).

### Environment Variables

#### Required

| Variable | Description |
|----------|-------------|
| `DISCORD__TOKEN` | Bot token from the [Developer Portal](https://discord.com/developers/applications) |
| `DISCORD__OWNER_IDS` | JSON array of Discord user IDs for owner-only commands, e.g. `[123456789]` |
| `DISCORD__GUILD_IDS` | JSON array of guild IDs where the bot should operate, e.g. `[111,222]` |

#### General

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Runtime environment (`development`, `production`, `test`) |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `DEBUG` | `false` | Enable debug mode |
| `SYNC_ON_STARTUP` | `false` | Sync slash commands to Discord on startup |

#### Discord

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD__COMMAND_PREFIX` | `!` | Prefix for text commands |
| `DISCORD__TEST_GUILD_IDS` | `[]` | Guild IDs for faster command sync during development |

#### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE__URL` | `sqlite:///data/bot.db` | Database connection URL |
| `DATABASE__ECHO` | `false` | Log SQL queries |
| `DATABASE__BUSY_TIMEOUT_MS` | `5000` | SQLite busy timeout in milliseconds (1000-30000) |
| `DATABASE__CONNECTION_TIMEOUT_S` | `10` | Connection timeout in seconds (1-60) |

#### Audio

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIO__DEFAULT_VOLUME` | `0.5` | Default playback volume (0.0-2.0) |
| `AUDIO__MAX_QUEUE_SIZE` | `50` | Maximum tracks per queue (1-1000) |
| `AUDIO__POT_SERVER_URL` | `http://127.0.0.1:4416` | URL of the bgutil POT provider for bypassing YouTube bot detection |

#### AI (Optional - powers `/radio`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AI__API_KEY` | *(empty)* | OpenAI API key. Radio feature is disabled without this |
| `AI__MODEL` | `gpt-5-mini` | Model to use for recommendations |
| `AI__MAX_TOKENS` | `500` | Max response tokens (1-4096) |
| `AI__TEMPERATURE` | `0.7` | Response randomness (0.0-2.0) |
| `AI__CACHE_TTL_SECONDS` | `3600` | How long to cache recommendations in seconds |

#### Voting

| Variable | Default | Description |
|----------|---------|-------------|
| `VOTING__SKIP_THRESHOLD_PERCENTAGE` | `0.5` | Fraction of listeners needed to skip (0.0-1.0) |
| `VOTING__MIN_VOTERS` | `1` | Minimum votes required to skip |
| `VOTING__AUTO_SKIP_LISTENER_COUNT` | `2` | If this many or fewer listeners, anyone can skip without voting |

#### Radio

| Variable | Default | Description |
|----------|---------|-------------|
| `RADIO__DEFAULT_COUNT` | `5` | Songs to add per radio fill (1-10) |
| `RADIO__MAX_TRACKS_PER_SESSION` | `50` | Max AI-generated tracks per radio session to cap API costs (1-200) |

#### Cleanup

| Variable | Default | Description |
|----------|---------|-------------|
| `CLEANUP__STALE_SESSION_HOURS` | `24` | Hours before an idle session is cleaned up |
| `CLEANUP__CLEANUP_INTERVAL_MINUTES` | `30` | How often the cleanup task runs |

## Commands

### Music

| Command | Description |
|---------|-------------|
| `/play <query>` | Play a song by URL or search query |
| `/skip` | Vote to skip (or force skip with admin) |
| `/stop` | Stop playback and clear the queue |
| `/pause` | Pause the current track |
| `/resume` | Resume paused playback |
| `/queue [page]` | Show the current queue |
| `/current` | Show the currently playing track |
| `/shuffle` | Shuffle the queue |
| `/loop` | Toggle loop mode (off / track / queue) |
| `/remove <pos>` | Remove a track by position |
| `/clear` | Clear the entire queue |
| `/radio` | Toggle AI radio - auto-queue similar songs |
| `/leave` | Disconnect from voice |

### Admin (Owner Only)

| Command | Description |
|---------|-------------|
| `/sync` | Sync slash commands to Discord |
| `/reload <cog>` | Hot-reload a cog |
| `/shutdown` | Gracefully shut down the bot |
| `/db-stats` | Show database statistics |
| `/db-cleanup` | Trigger manual cleanup |
| `/cache-status` | Show AI recommendation cache stats |
| `/cache-clear` | Clear the recommendation cache |

### Info

| Command | Description |
|---------|-------------|
| `/ping` | Check bot latency |
| `/uptime` | Show bot uptime |
| `/stats` | Show bot statistics |
| `/played` | Show recently played tracks |

## Running in Production

The `music_start.py` script manages the bot inside a detached [tmux](https://github.com/tmux/tmux) session, providing process lifecycle management and optional auto-restart on crash. Requires `tmux` to be installed (`apt install tmux` or `brew install tmux`).

### Subcommands

| Command | Description |
|---------|-------------|
| `./music_start.py start` | Start the bot in a detached tmux session |
| `./music_start.py stop` | Stop the bot and kill the tmux session |
| `./music_start.py restart` | Stop then start the bot |
| `./music_start.py attach` | Attach to the running tmux session (Ctrl+B, D to detach) |
| `./music_start.py status` | Show whether the session is running |

### Flags

| Flag | Description |
|------|-------------|
| `--respawn` | Auto-restart the bot if it crashes (recommended for production) |
| `--log-file PATH` | Log file path (default: `logs/music_bot.log`) |
| `--session NAME` | tmux session name (default: `music_bot`) |
| `--cmd CMD` | Override the bot command (default: auto-detects `discord-music-player` or falls back to `python src/discord_music_player/main.py`) |

### Examples

```bash
# Start with auto-restart (recommended)
./music_start.py start --respawn

# Start with custom log location
./music_start.py start --respawn --log-file /var/log/music_bot.log

# View live logs
tail -f logs/music_bot.log

# Attach to see real-time output (Ctrl+B, D to detach)
./music_start.py attach

# Restart after a config change
./music_start.py restart --respawn
```

There is also a Makefile shortcut: `make run-tmux` runs `./music_start.py start --respawn`.

### Docker Deployment

Run the full stack (bot + POT provider) with a single command:

```bash
# Configure your .env first
make setup-env
# Edit .env with your Discord token

# Start everything
docker compose up -d

# View logs
docker compose logs -f music-bot

# Stop everything
docker compose down
```

The `docker-compose.yml` includes:
- **bgutil-provider** — YouTube POT token generator with health checks
- **music-bot** — the bot itself, built from the included `Dockerfile`

The bot service automatically:
- Waits for the POT provider to be healthy before starting
- Uses the container hostname (`bgutil-provider:4416`) instead of localhost
- Mounts `data/` and `logs/` as volumes for persistence
- Restarts on failure (`unless-stopped`)

### Systemd Deployment

For running the bot as a native Linux service (without Docker or tmux):

1. Copy the service file:
   ```bash
   sudo cp discord-music-bot.service /etc/systemd/system/
   ```

2. Edit the paths and username:
   ```bash
   sudo systemctl edit discord-music-bot
   ```

3. Enable and start:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable discord-music-bot
   sudo systemctl start discord-music-bot
   ```

4. View logs:
   ```bash
   journalctl -u discord-music-bot -f
   ```

The service file includes security hardening (`NoNewPrivileges`, `ProtectSystem`, `PrivateTmp`) and a 30-second graceful shutdown timeout.

## Development

### Makefile Commands

Run `make help` to see all available targets. Below is the full reference:

#### Setup

| Command | Description |
|---------|-------------|
| `make setup` | Full first-time setup: checks prereqs, creates `.venv`, installs deps, creates `.env`, starts POT provider |
| `make prereqs` | Check that Python 3.12+, ffmpeg, Docker, and docker-compose are installed |
| `make install` | Install production dependencies (`pip install -e .`) |
| `make dev` | Install with dev and test dependencies (`pip install -e ".[dev,test]"`) |
| `make setup-env` | Create `.env` from `.env.example` (skips if `.env` exists) |

#### Quality

| Command | Description |
|---------|-------------|
| `make test` | Run tests with pytest |
| `make test-cov` | Run tests with coverage report (HTML output in `htmlcov/`) |
| `make lint` | Lint with ruff |
| `make format` | Auto-format code with ruff |
| `make check` | Run lint + tests together |

#### Running

| Command | Description |
|---------|-------------|
| `make run` | Run the bot directly (requires `.env` file) |
| `make run-tmux` | Run the bot in tmux with auto-respawn (uses `music_start.py`) |

#### Database

| Command | Description |
|---------|-------------|
| `make db-reset` | Delete the SQLite database files (interactive confirmation) |

#### YouTube POT Provider

The POT (Proof of Origin Token) provider is a Docker container that generates tokens to prevent YouTube 403 errors. It must be running for YouTube playback to work reliably.

| Command | Description |
|---------|-------------|
| `make pot-start` | Start the bgutil POT provider container |
| `make pot-stop` | Stop the POT provider container |
| `make pot-logs` | Tail the POT provider logs |
| `make pot-status` | Check if the POT provider is running |

#### Utilities

| Command | Description |
|---------|-------------|
| `make clean` | Remove `__pycache__`, `.egg-info`, `.pytest_cache`, `.ruff_cache`, coverage files |
| `make info` | Show Python version and installed dependency versions |
| `make help` | Show all available make targets |

### Project Structure

```
src/discord_music_player/
  domain/             # Business logic (entities, value objects, services)
  application/        # Use cases (commands, queries, services)
  infrastructure/     # External adapters (Discord, yt-dlp, FFmpeg, SQLite, OpenAI)
  config/             # Settings and dependency injection container
```

## Troubleshooting

### YouTube 403 Errors

The POT (Proof of Origin Token) provider must be running for YouTube playback. See [docs/POT_PROVIDER_SETUP.md](docs/POT_PROVIDER_SETUP.md) for full details.

```bash
# Check if POT provider is running
make pot-status

# Restart it
make pot-start

# Update yt-dlp (fixes most extraction issues)
pip install --upgrade yt-dlp bgutil-ytdlp-pot-provider
```

### Bot Won't Join Voice Channel

1. **Check bot permissions** — the bot needs `Connect` and `Speak` permissions in the voice channel
2. **Check intents** — ensure `Server Members` and `Message Content` intents are enabled in the [Developer Portal](https://discord.com/developers/applications)
3. **Check ffmpeg** — run `ffmpeg -version` to confirm it's installed
4. **Check PyNaCl** — run `python -c "import nacl"` — if it fails, install system deps (see [Prerequisites](#system-packages-linux))

### Bot Not Responding to Commands

1. **Check slash commands are synced** — set `SYNC_ON_STARTUP=true` in `.env` or use `/sync` (owner only)
2. **Check guild IDs** — ensure `DISCORD__GUILD_IDS` includes your server's ID
3. **Check logs** — `tail -f logs/music_bot.log` or `make pot-logs`

### Audio Cuts Out or Skips

- Increase FFmpeg reconnect settings (already configured in defaults)
- Check network stability between bot host and Discord
- If running in Docker, ensure the container has sufficient resources

### Database Issues

```bash
# Check database stats via Discord
/db-stats

# Reset the database (deletes all data)
make db-reset
```

## License

BSD 3-Clause License - see [LICENSE](LICENSE) for details. Attribution required.
