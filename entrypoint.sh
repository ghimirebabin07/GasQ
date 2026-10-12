#!/bin/sh

echo "==> Starting GasQ application server..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
