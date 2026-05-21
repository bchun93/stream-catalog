#!/usr/bin/env bash
# Start API — run from macOS Terminal.app (not Cursor) if TMDB DNS fails.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"

if lsof -ti ":${PORT}" >/dev/null 2>&1; then
  echo "Stopping existing process on port ${PORT}..."
  kill $(lsof -ti ":${PORT}") 2>/dev/null || kill -9 $(lsof -ti ":${PORT}") 2>/dev/null || true
  sleep 1
fi

cd "$ROOT/backend"
source .venv/bin/activate
unset TMDB_API_KEY HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy NO_PROXY

echo "Starting Stream Catalog API on http://127.0.0.1:${PORT}"
echo "Test TMDB: curl http://127.0.0.1:${PORT}/api/v1/metadata/health"
exec uvicorn app.main:app --reload --host 127.0.0.1 --port "${PORT}"
