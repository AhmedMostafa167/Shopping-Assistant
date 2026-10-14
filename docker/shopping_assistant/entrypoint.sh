#!/bin/bash
set -e

echo "Running database migrations..."
cd /app/models/db_schemes/shopping_assistant
alembic upgrade head
cd /app

# Metrics files from a previous run would be added to this run's counts.
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -rf "$PROMETHEUS_MULTIPROC_DIR" && mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

echo "Starting FastAPI..."
exec "$@"