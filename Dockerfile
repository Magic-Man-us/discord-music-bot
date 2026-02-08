FROM python:3.12-slim AS base

# System dependencies for PyNaCl (voice) and ffmpeg (audio playback)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || true

# Copy source code
COPY src/ src/
COPY music_start.py ./

# Re-install now that source is present (editable install needs src/)
RUN pip install --no-cache-dir -e .

# Create directories for persistent data
RUN mkdir -p data logs

# Non-root user for security
RUN useradd -r -s /bin/false botuser && chown -R botuser:botuser /app
USER botuser

EXPOSE 8080

ENTRYPOINT ["discord-music-player"]
