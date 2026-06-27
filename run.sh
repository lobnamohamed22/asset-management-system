#!/bin/bash
set -e

echo "Waiting for PostgreSQL to start..."
while ! nc -z db 5432; do
  sleep 0.5
done
echo "PostgreSQL is up and running!"

echo "Running database migrations..."
alembic upgrade head

echo "Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
