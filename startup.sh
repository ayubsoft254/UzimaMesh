#!/bin/bash
# startup.sh - Azure App Service Startup Script for Django

set -e  # Exit on any unhandled error

# ─── 1. Wait for PostgreSQL to be ready (max 30s) ───────────────────────────
echo "Waiting for database to be ready..."
MAX_WAIT=30
WAITED=0
until python -c "
import os, sys, dj_database_url, psycopg2
url = os.environ.get('DATABASE_URL')
if not url:
    sys.exit(0)  # SQLite — no wait needed
cfg = dj_database_url.parse(url)
try:
    conn = psycopg2.connect(
        host=cfg['HOST'], port=cfg.get('PORT', 5432),
        dbname=cfg['NAME'], user=cfg['USER'], password=cfg['PASSWORD'],
        connect_timeout=5, sslmode='require'
    )
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'DB not ready: {e}', flush=True)
    sys.exit(1)
" 2>/dev/null; do
    if [ "$WAITED" -ge "$MAX_WAIT" ]; then
        echo "ERROR: Database not reachable after ${MAX_WAIT}s. Aborting startup."
        exit 1
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "DB ready (waited ${WAITED}s)."

# ─── 2. Run migrations (60s timeout) ────────────────────────────────────────
echo "Running database migrations..."
timeout 60 python manage.py migrate --noinput || {
    echo "ERROR: migrate failed or timed out. Check DB connectivity and migration files."
    exit 1
}

# ─── 3. Seed test data (only when explicitly requested) ─────────────────────
if [ "${SEED_ON_STARTUP}" = "true" ]; then
    echo "Seeding test data..."
    python manage.py seed_data
else
    echo "Skipping seed data (set SEED_ON_STARTUP=true to enable)."
fi

# ─── 4. Start Gunicorn with ASGI worker ─────────────────────────────────────
echo "Starting Gunicorn (ASGI)..."
exec gunicorn \
    --bind=0.0.0.0:8000 \
    --timeout=600 \
    --workers=2 \
    --worker-class=uvicorn.workers.UvicornWorker \
    --access-logfile=- \
    --error-logfile=- \
    uzima_mesh.asgi:application
