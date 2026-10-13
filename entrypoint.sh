#!/bin/sh
set -e

echo "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until python -c "import socket, os, sys; s=socket.socket(); s.settimeout(1); \
sys.exit(0 if s.connect_ex((os.environ['POSTGRES_HOST'], int(os.environ['POSTGRES_PORT'])))==0 else 1)"; do
    sleep 1
done

echo "PostgreSQL is up. Applying migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput || true

echo "Starting: $@"
exec "$@"
