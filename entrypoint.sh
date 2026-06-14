#!/bin/sh
set -e

echo "Applying database migrations via Alembic..."
alembic upgrade head

echo "Starting Uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
