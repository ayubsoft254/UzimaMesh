#!/bin/bash
# startup.sh - Azure App Service Startup Script for Django

# 1. Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# 2. Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# 3. Seed test data
echo "Seeding test data..."
python manage.py seed_data

# 4. Start Gunicorn with ASGI worker
echo "Starting Gunicorn (ASGI)..."
gunicorn --bind=0.0.0.0 --timeout 600 -k uvicorn.workers.UvicornWorker uzima_mesh.asgi:application
