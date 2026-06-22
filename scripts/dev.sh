#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT/backend/.env" ]] && grep -q '^AWS_ENDPOINT_URL=' "$ROOT/backend/.env"; then
  if ! lsof -ti :9000 >/dev/null 2>&1; then
    echo "Starting local MinIO on :9000"
    export MINIO_ROOT_USER="${MINIO_ROOT_USER:-streamcatalog}"
    export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-streamcatalog-dev-secret}"
    "$ROOT/scripts/start-minio.sh" &
    sleep 2
  fi
fi

echo "Starting Relay API on :8000"
cd "$ROOT/backend"
source .venv/bin/activate
unset TMDB_API_KEY HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!

echo "Starting admin UI on :5173"
cd "$ROOT/frontend"
npm run dev &
UI_PID=$!

trap 'kill $API_PID $UI_PID 2>/dev/null' EXIT
wait
