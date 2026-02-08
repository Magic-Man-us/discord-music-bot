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

- **Python 3.11+**
- **FFmpeg** - [ffmpeg.org](https://ffmpeg.org/)
- **Docker** - For the YouTube POT provider ([Install Docker](https://docs.docker.com/get-docker/))
- **Discord Bot Token** - [Developer Portal](https://discord.com/developers/applications) with Message Content and Server Members intents enabled

## Quick Start

```bash
# Clone and install
git clone https://github.com/Magic-Man-us/discord-music-bot.git
cd discord-music-bot
make install

# Start YouTube POT provider (prevents 403 errors)
make pot-start

# Configure environment
make setup-env
# Edit .env with your Discord token and settings

# Run the bot
make run
```

The database is created automatically on first run.

## Configuration

Copy `.env.example` to `.env` and edit it. Key settings:

```env
# Required
DISCORD__TOKEN=your_discord_bot_token
DISCORD__OWNER_IDS=[your_discord_user_id]
DISCORD__GUILD_IDS=[guild_id_1,guild_id_2]

# Optional - AI Radio (requires OpenAI API key)
AI__API_KEY=your_openai_api_key
AI__MODEL=gpt-4o-mini
```

All settings use Pydantic nested delimiter format (`SECTION__KEY`). See `.env.example` for the full list with defaults.

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
| `/sql <query>` | Execute a raw SQL query |
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

## Development

```bash
make dev        # Install with dev dependencies
make test       # Run tests
make test-cov   # Run tests with coverage report
make lint       # Lint with ruff
make format     # Auto-format code
make check      # Lint + tests
```

### Project Structure

```
src/discord_music_player/
  domain/             # Business logic (entities, value objects, services)
  application/        # Use cases (commands, queries, services)
  infrastructure/     # External adapters (Discord, yt-dlp, FFmpeg, SQLite, OpenAI)
  config/             # Settings and dependency injection container
```

## License

BSD 3-Clause License - see [LICENSE](LICENSE) for details. Attribution required.
