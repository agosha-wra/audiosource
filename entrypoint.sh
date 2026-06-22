#!/bin/bash
set -e

echo "Starting AudioSource..."

# --------------------------------------------------------------------
# Drop-privileges setup
#
# All files written by the backend (downloaded album folders, scanned
# library files, etc.) should be owned by a regular host user so that
# other apps on the host (e.g. Jellyfin) can manage them. We honor the
# common PUID/PGID pattern for this; default to 1000:1000.
#
# nginx still runs as root so it can bind to port 80 and serve static
# frontend files; only the backend (which writes to the music folder)
# is dropped to the unprivileged user.
# --------------------------------------------------------------------
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Configuring audiosource user to ${PUID}:${PGID}"
groupmod -o -g "$PGID" audiosource
usermod  -o -u "$PUID" -g "$PGID" audiosource

# 002 makes new files 664 / new dirs 775 (group-writable). Combined with
# the setgid bit your music folder already carries, files inherit the
# right group and remain deletable by anyone in that group.
umask 0002

# Wait for PostgreSQL to be ready using pg_isready equivalent
echo "Waiting for PostgreSQL at db:5432..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if python3 -c "
import socket
import sys
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(('db', 5432))
    sock.close()
    sys.exit(0 if result == 0 else 1)
except Exception as e:
    print(f'Connection attempt failed: {e}')
    sys.exit(1)
" 2>&1; then
        echo "PostgreSQL is accepting connections!"
        break
    fi
    attempt=$((attempt + 1))
    echo "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
    sleep 1
done

if [ $attempt -eq $max_attempts ]; then
    echo "ERROR: Could not connect to PostgreSQL after $max_attempts attempts"
    exit 1
fi

# Give PostgreSQL a moment to be fully ready
sleep 2

# The umask set above is inherited through runuser.
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ms-playwright}"

# Start nginx in background (still root, so it can bind port 80)
echo "Starting nginx..."
nginx -g "daemon off;" &

# Start the FastAPI backend as the unprivileged audiosource user so any
# files it writes to bind-mounted volumes are owned by ${PUID}:${PGID}.
# The umask set above is inherited through runuser.
echo "Starting FastAPI backend as audiosource (${PUID}:${PGID})..."
cd /app/backend
exec runuser -u audiosource -- uvicorn app.main:app --host 0.0.0.0 --port 8000
