#!/bin/bash
# startup.sh - Azure App Service Startup Script for Django

# 1. Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# 2. Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# 3. Seed test users
echo "Seeding test users..."
python seed_users.py

# 4. Start Gunicorn
echo "Starting Gunicorn..."
gunicorn --bind=0.0.0.0 --timeout 600 uzima_mesh.wsgi
