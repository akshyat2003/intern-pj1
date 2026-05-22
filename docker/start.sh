#!/bin/sh
set -eu

cd /app/backend
/app/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "${BACKEND_PORT:-8000}" &
backend_pid=$!

cd /app/frontend
PORT="${PORT:-3000}" HOSTNAME=0.0.0.0 npm run start &
frontend_pid=$!

stop_services() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
}

trap stop_services INT TERM

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 2
done

stop_services
wait "$backend_pid" 2>/dev/null || true
wait "$frontend_pid" 2>/dev/null || true
