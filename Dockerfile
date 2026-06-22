# Multi-stage build for AudioSource

# Stage 1: Build the React frontend
# Run on the host's native architecture to avoid QEMU emulation crashes
# (esbuild segfaults under QEMU when cross-building amd64 from arm64).
# The output is static JS/HTML/CSS and is architecture-independent.
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend (bookworm — stable apt; slim tag tracks trixie and breaks QEMU cross-builds)
FROM python:3.11-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MUSIC_FOLDER=/music \
    PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

WORKDIR /app

# QEMU cross-builds (arm64 host → amd64 image) often have clock skew; without this,
# apt rejects Release signatures as "created after the --not-after date".
RUN printf '%s\n' \
    'Acquire::Check-Valid-Until "false";' \
    'Acquire::Check-Date "false";' \
    > /etc/apt/apt.conf.d/99no-check-valid-until

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# System deps + Playwright Chromium + nginx in one apt layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libatspi2.0-0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libx11-6 libxcb1 libxext6 libglib2.0-0 fonts-liberation \
    nginx \
    && mkdir -p /opt/ms-playwright \
    && playwright install chromium \
    && chmod -R a+rX /opt/ms-playwright \
    && groupadd -g 1000 audiosource \
    && useradd -u 1000 -g 1000 -m -s /bin/bash audiosource \
    && rm -rf /var/lib/apt/lists/*

# Install beets for music tagging with deezer and spotify plugins
RUN pip install --no-cache-dir beets requests deezer-python spotipy

# Copy backend code
COPY backend/ ./backend/

# Copy frontend built assets
COPY --from=frontend /app/frontend/dist /app/frontend

# Configure nginx
COPY nginx.conf /etc/nginx/nginx.conf

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/entrypoint.sh"]
