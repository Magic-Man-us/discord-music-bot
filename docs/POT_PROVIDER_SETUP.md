# PO Token Provider Setup

## What is bgutil-ytdlp-pot-provider?

The `bgutil-ytdlp-pot-provider` is a service that generates Proof of Origin (PO) tokens required to bypass YouTube's bot detection. These tokens are automatically used by yt-dlp to access YouTube content without being blocked.

## Quick Start

### Option 1: Using Docker Compose (Recommended)

1. **Start the POT provider:**
   ```bash
   docker-compose up -d bgutil-provider
   ```

2. **Verify it's running:**
   ```bash
   docker ps | grep bgutil-provider
   curl http://localhost:4416/
   ```

3. **Run your bot:**
   ```bash
   python music_start.py
   # or
   make run
   ```

The bot will automatically connect to the POT provider on `http://127.0.0.1:4416`.

### Option 2: Manual Docker Setup

```bash
docker run -d \
  --name bgutil-provider \
  --restart unless-stopped \
  -p 4416:4416 \
  ghcr.io/brainicism/bgutil-ytdlp-pot-provider:latest
```

## Configuration

### Environment Variables

Configure the POT provider in your `.env` file:

```bash
# POT Provider Configuration
POT_SERVER_URL=http://127.0.0.1:4416  # Default value
```

### Custom Port

To use a different port:

1. Update `docker-compose.yml`:
   ```yaml
   ports:
     - "5000:4416"  # Host:Container
   ```

2. Update your `.env`:
   ```bash
   POT_SERVER_URL=http://127.0.0.1:5000
   ```

## Distribution for Other Users

### Method 1: Docker Compose (Simplest)

Share these files with your users:
- `docker-compose.yml`
- `docs/POT_PROVIDER_SETUP.md` (this file)
- `.env.example`

**User Setup Instructions:**
```bash
# 1. Copy docker-compose.yml to your project
# 2. Start the POT provider
docker-compose up -d bgutil-provider

# 3. Configure your bot
cp .env.example .env
# Edit .env with your Discord token and settings

# 4. Install and run
make install
make run
```

### Method 2: System Service (Advanced)

For users who want to run the POT provider as a system service:

1. **Create systemd service** (`/etc/systemd/system/bgutil-pot-provider.service`):
   ```ini
   [Unit]
   Description=bgutil POT Provider
   After=docker.service
   Requires=docker.service

   [Service]
   Type=simple
   Restart=always
   ExecStartPre=-/usr/bin/docker stop bgutil-provider
   ExecStartPre=-/usr/bin/docker rm bgutil-provider
   ExecStart=/usr/bin/docker run --rm --name bgutil-provider \
     -p 4416:4416 \
     ghcr.io/brainicism/bgutil-ytdlp-pot-provider:latest
   ExecStop=/usr/bin/docker stop bgutil-provider

   [Install]
   WantedBy=multi-user.target
   ```

2. **Enable and start:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable bgutil-pot-provider
   sudo systemctl start bgutil-pot-provider
   ```

### Method 3: Include in Bot Installation

Add to your `README.md` installation section:

```markdown
## Prerequisites

1. **Install Docker** (required for POT provider):
   - [Docker Desktop](https://www.docker.com/products/docker-desktop) (Windows/Mac)
   - Docker Engine (Linux): `curl -fsSL https://get.docker.com | sh`

2. **Start POT Provider:**
   ```bash
   docker-compose up -d bgutil-provider
   ```

3. **Install Bot:**
   ```bash
   make install
   ```
```

## Verification

### Test POT Provider

```bash
# Check if container is running
docker ps | grep bgutil-provider

# Test the endpoint
curl http://localhost:4416/

# View logs
docker logs bgutil-provider
```

### Test Bot Integration

Run the integration test:
```bash
python -m pytest tests/test_ytdlp_resolver.py::TestPOTProviderConfiguration -v
```

Or use the verification script:
```python
from discord_music_player.infrastructure.audio.ytdlp_resolver import YtDlpResolver
from discord_music_player.config.settings import AudioSettings

settings = AudioSettings()
resolver = YtDlpResolver(settings)
opts = resolver._get_opts()

print(f"✓ POT Server: {settings.pot_server_url}")
print(f"✓ Configured: {opts['extractor_args']['youtube']['pot_server_url']}")
```

## Troubleshooting

### POT Provider not responding

```bash
# Restart the container
docker-compose restart bgutil-provider

# Check logs for errors
docker logs bgutil-provider --tail 50
```

### Bot can't connect to POT provider

1. **Check container is running:**
   ```bash
   docker ps | grep bgutil-provider
   ```

2. **Verify port is accessible:**
   ```bash
   curl http://localhost:4416/
   ```

3. **Check firewall settings:**
   ```bash
   # Linux
   sudo ufw status

   # Ensure port 4416 is not blocked
   ```

4. **Verify bot configuration:**
   ```bash
   python -c "from discord_music_player.config.settings import AudioSettings; print(AudioSettings().pot_server_url)"
   ```

### YouTube 403 errors persist

1. **Ensure POT provider is generating tokens:**
   ```bash
   docker logs bgutil-provider | grep "poToken:"
   ```

2. **Update bgutil-ytdlp-pot-provider plugin:**
   ```bash
   pip install --upgrade bgutil-ytdlp-pot-provider
   ```

3. **Update yt-dlp:**
   ```bash
   pip install --upgrade yt-dlp
   ```

## Additional Resources

- [bgutil-ytdlp-pot-provider GitHub](https://github.com/brainicism/bgutil-ytdlp-pot-provider)
- [yt-dlp Documentation](https://github.com/yt-dlp/yt-dlp)
- [Docker Documentation](https://docs.docker.com/)

## License Note

The `bgutil-ytdlp-pot-provider` is a separate project with its own license. Ensure compliance when distributing.
