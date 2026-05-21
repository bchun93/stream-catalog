#!/usr/bin/env bash
# Full local restart — run in Terminal.app: ./scripts/restart-all.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

for port in 8001 8002 8003 5173; do
  if lsof -ti ":${port}" >/dev/null 2>&1; then
    echo "Freeing port ${port}..."
    kill $(lsof -ti ":${port}") 2>/dev/null || kill -9 $(lsof -ti ":${port}") 2>/dev/null || true
  fi
done
sleep 2

export PORT=8000
"$ROOT/scripts/start-backend.sh" &
sleep 3

cd "$ROOT/frontend"
npm run dev
