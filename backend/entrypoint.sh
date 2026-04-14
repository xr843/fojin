#!/bin/sh
set -e

echo "[FoJin] Running database migrations..."
alembic upgrade head

echo "[FoJin] Seeding hot questions..."
python -m scripts.seed_hot_questions || echo "[FoJin] hot question seed failed — continuing"

echo "[FoJin] Starting backend server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
