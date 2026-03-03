#!/bin/sh
set -eu

attempts=30

while [ "$attempts" -gt 0 ]; do
  if alembic upgrade head; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
  fi

  attempts=$((attempts - 1))
  echo "alembic upgrade failed, retrying in 2s..."
  sleep 2
done

echo "database migrations failed after retries" >&2
exit 1
