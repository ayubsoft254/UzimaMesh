#!/bin/bash
set -e

# Run database migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Gunicorn
echo "Starting Gunicorn..."
gunicorn uzima_mesh.wsgi:application --bind 0.0.0.0:8000
