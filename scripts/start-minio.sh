#!/usr/bin/env bash
# Local S3-compatible storage (MinIO) for stream-catalog development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$ROOT/data/minio"
MINIO_BIN="${MINIO_BIN:-$HOME/.local/bin/minio}"
API_PORT="${MINIO_API_PORT:-9000}"
CONSOLE_PORT="${MINIO_CONSOLE_PORT:-9001}"

export MINIO_ROOT_USER="${MINIO_ROOT_USER:-streamcatalog}"
export MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:-streamcatalog-dev-secret}"

mkdir -p "$DATA_DIR"

if ! command -v "$MINIO_BIN" >/dev/null 2>&1 && [[ ! -x "$MINIO_BIN" ]]; then
  echo "MinIO not found. Run: ./scripts/setup-local-s3.sh" >&2
  exit 1
fi

if lsof -ti ":${API_PORT}" >/dev/null 2>&1; then
  echo "MinIO already running on port ${API_PORT}"
  exit 0
fi

echo "Starting MinIO API :${API_PORT}  Console :${CONSOLE_PORT}"
echo "  Console: http://127.0.0.1:${CONSOLE_PORT}"
exec "$MINIO_BIN" server "$DATA_DIR" --address ":${API_PORT}" --console-address ":${CONSOLE_PORT}"
