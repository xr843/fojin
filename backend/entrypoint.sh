#!/bin/sh
set -e

echo "[FoJin] Running database migrations..."
alembic upgrade head

echo "[FoJin] Seeding hot questions..."
python -m scripts.seed_hot_questions || echo "[FoJin] hot question seed failed — continuing"

echo "[FoJin] Starting backend server..."
# --proxy-headers: trust X-Forwarded-* set by upstream nginx so
# request.client.host and request.url.scheme reflect the real client
# rather than the docker bridge IP.
# --forwarded-allow-ips: only trust XFF/XFP from the docker bridge
# (nginx container). Defaults to 127.0.0.1 which would silently ignore
# proxy headers since nginx connects from a private docker IP.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
