#!/bin/sh
set -e

echo "[FoJin] Running database migrations..."
alembic upgrade head

echo "[FoJin] Seeding hot questions..."
python -m scripts.seed_hot_questions || echo "[FoJin] hot question seed failed — continuing"

echo "[FoJin] Starting backend server..."
# Intentionally NOT passing --proxy-headers. nginx forwards
# X-Forwarded-For via $proxy_add_x_forwarded_for which APPENDS the real
# client IP to the right of any client-supplied value. uvicorn's
# --proxy-headers picks the LEFTMOST entry, which is exactly the
# spoofable claim. Application code reads the real IP via
# app.core.client_ip.get_real_client_ip (last entry of XFF). Access
# logs will show the docker bridge IP instead of the real client —
# acceptable trade for not trusting client-supplied headers.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000
