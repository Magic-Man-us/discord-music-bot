FROM python:3.14-slim

# System dependencies for PyNaCl (voice) and ffmpeg (audio playback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata first (cached layer for dependency installs)
COPY pyproject.toml ./

# Copy source code
COPY src/ src/
COPY music_start.py ./

# Production install (non-editable)
RUN pip install --no-cache-dir .

# Create directories for persistent data
RUN mkdir -p data logs

# Non-root user for security
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app
USER botuser

ENTRYPOINT ["discord-music-player"]
