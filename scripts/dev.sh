#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting Stream Catalog API on :8000"
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
