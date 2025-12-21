#!/bin/bash
set -e

echo "Starting AudioSource..."

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

# Start nginx in background
echo "Starting nginx..."
nginx -g "daemon off;" &

# Start the FastAPI backend
echo "Starting FastAPI backend..."
cd /app/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
