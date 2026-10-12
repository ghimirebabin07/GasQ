#!/bin/sh
set -e

echo "==> Running database migrations with Alembic..."
alembic upgrade head || {
    echo "Warning: Alembic migration reported an issue or already at head. Continuing..."
}

echo "==> Starting GasQ application server..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
