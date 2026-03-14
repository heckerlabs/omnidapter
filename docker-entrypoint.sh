#!/bin/sh
set -e

cd /app/apps/omnidapter-api

echo "Running database migrations..."
uv run alembic upgrade head

echo "Starting server on port ${PORT:-8000}..."
exec uv run uvicorn omnidapter_api.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --proxy-headers \
    --forwarded-allow-ips '*'
