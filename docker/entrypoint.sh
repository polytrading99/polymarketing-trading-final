#!/usr/bin/env bash
set -euo pipefail

# Only run migrations for backend/API service (uvicorn)
if [ "${1:-}" = "uvicorn" ]; then
  echo "Running database migrations..."
  # Use the existing venv directly
  /app/.venv/bin/python -m alembic upgrade head
fi

exec "$@"

