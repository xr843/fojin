#!/bin/sh
set -e

echo "[FoJin] Running database migrations..."
alembic upgrade head

echo "[FoJin] Starting backend server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
