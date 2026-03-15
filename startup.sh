#!/bin/bash
# startup.sh - Azure App Service Startup Script for Django

# NOTE: Do NOT use `set -e` here. If DB is temporarily unreachable we log a
# warning and continue so gunicorn still starts and the warmup probe succeeds.
# A crash-loop (exit 1 → container restart → repeat) would exhaust the
# WEBSITES_CONTAINER_START_TIME_LIMIT window before the app ever binds a port.

# ─── 1. Wait for PostgreSQL to be ready (max 120s) ──────────────────────────
echo "Waiting for database to be ready..."
DB_READY=false
MAX_WAIT=120
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
        echo "WARNING: Database not reachable after ${MAX_WAIT}s. Skipping migrations and continuing."
        break
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ "$WAITED" -lt "$MAX_WAIT" ]; then
    echo "DB ready (waited ${WAITED}s)."
    DB_READY=true
fi

# ─── 2. Collect static files (no DB required) ───────────────────────────────
echo "Collecting static files..."
python manage.py collectstatic --noinput || echo "WARNING: collectstatic failed — continuing anyway."

# ─── 3. Run migrations (90s timeout, non-fatal) ─────────────────────────────
if [ "$DB_READY" = "true" ]; then
    echo "Running database migrations..."
    timeout 90 python manage.py migrate --noinput || \
        echo "WARNING: migrate failed or timed out. The app will start but may be degraded."
fi

# ─── 4. Seed test data (only when explicitly requested) ─────────────────────
if [ "${SEED_ON_STARTUP}" = "true" ]; then
    echo "Flushing database..."
    python manage.py flush --noinput
    echo "Seeding test data..."
    python manage.py seed_data
else
    echo "Skipping seed data (set SEED_ON_STARTUP=true to enable)."
fi

# ─── 4. Start Gunicorn with ASGI worker ─────────────────────────────────────
echo "Starting Gunicorn (ASGI)..."
# MCP over SSE stores active session writers in-process. If multiple Gunicorn
# workers are used, the SSE handshake may hit one worker while /mcp/messages
# lands on another worker, causing MCP tool POSTs to return 404.
# Keep a single worker by default unless you provide an MCP-aware routing strategy.
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
echo "Using GUNICORN_WORKERS=${GUNICORN_WORKERS}"

PORT="${PORT:-8000}"
echo "Binding gunicorn to 0.0.0.0:${PORT}"

exec gunicorn \
    --bind=0.0.0.0:"${PORT}" \
    --timeout=0 \
    --keep-alive=75 \
    --workers="${GUNICORN_WORKERS}" \
    --worker-class=uvicorn.workers.UvicornWorker \
    --worker-connections=1000 \
    --access-logfile=- \
    --error-logfile=- \
    --log-level=info \
    uzima_mesh.asgi:application