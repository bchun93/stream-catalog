#!/usr/bin/env bash
set -euo pipefail

API_URL="${1:-https://stream-catalog.onrender.com}"
TITLE_ID="${TITLE_ID:-}"
MANIFEST_ID="${MANIFEST_ID:-}"
SOURCE_PREFIX="${SOURCE_PREFIX:-}"
ADMIN_TOKEN="${ADMIN_API_KEY:-}"

if [[ -z "${TITLE_ID}" || -z "${MANIFEST_ID}" ]]; then
  echo "Set TITLE_ID and MANIFEST_ID environment variables before running."
  echo "Example:"
  echo "  TITLE_ID=54 MANIFEST_ID=1 SOURCE_PREFIX=drop-2026 ./scripts/verify-ingest.sh https://stream-catalog.onrender.com"
  exit 1
fi

if [[ -z "${ADMIN_TOKEN}" ]]; then
  echo "Set ADMIN_API_KEY before running. Storage and ingest routes require X-Admin-Token."
  exit 1
fi
TOKEN_HEADER=(-H "X-Admin-Token: ${ADMIN_TOKEN}")

echo "== Diagnostics =="
curl -sS "${API_URL}/api/v1/diagnostics" | python3 -m json.tool

echo
echo "== Validate manifest =="
curl -sS "${API_URL}/api/v1/ingest/manifests/validate" \
  -H "Content-Type: application/json" \
  "${TOKEN_HEADER[@]}" \
  -d "$(cat <<EOF
{
  "manifest_id": ${MANIFEST_ID},
  "source_prefix": "${SOURCE_PREFIX}",
  "max_keys": 200
}
EOF
)" | python3 -m json.tool

echo
echo "== Run dry ingest job =="
curl -sS "${API_URL}/api/v1/ingest/jobs" \
  -H "Content-Type: application/json" \
  "${TOKEN_HEADER[@]}" \
  -d "$(cat <<EOF
{
  "title_id": ${TITLE_ID},
  "manifest_id": ${MANIFEST_ID},
  "source_prefix": "${SOURCE_PREFIX}",
  "dry_run": true,
  "created_by": "verify-ingest-script",
  "max_keys": 200
}
EOF
)" | python3 -m json.tool
