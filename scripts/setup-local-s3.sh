#!/usr/bin/env bash
# Bootstrap local MinIO bucket + project .env for stream-catalog Storage module.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUCKET="${INGEST_S3_BUCKET:-stream-catalog-ingest}"
REGION="${AWS_REGION:-us-east-1}"
ENDPOINT="${AWS_ENDPOINT_URL:-http://127.0.0.1:9000}"
ACCESS_KEY="${MINIO_ROOT_USER:-streamcatalog}"
SECRET_KEY="${MINIO_ROOT_PASSWORD:-streamcatalog-dev-secret}"
TOKEN_FILE="$ROOT/backend/.env"

if [[ -f "$TOKEN_FILE" ]] && grep -q '^INGEST_OPERATOR_TOKEN=' "$TOKEN_FILE"; then
  TOKEN="$(grep '^INGEST_OPERATOR_TOKEN=' "$TOKEN_FILE" | cut -d= -f2-)"
else
  TOKEN="$(openssl rand -hex 24)"
fi

source "$HOME/.local/bin/env" 2>/dev/null || true

if ! command -v minio >/dev/null 2>&1; then
  echo "Installing MinIO..."
  curl -fsSL "https://dl.min.io/server/minio/release/darwin-arm64/minio" \
    -o "$HOME/.local/bin/minio"
  chmod +x "$HOME/.local/bin/minio"
fi

if ! lsof -ti :9000 >/dev/null 2>&1; then
  echo "Starting MinIO in background..."
  MINIO_ROOT_USER="$ACCESS_KEY" MINIO_ROOT_PASSWORD="$SECRET_KEY" \
    "$ROOT/scripts/start-minio.sh" &
  sleep 2
fi

export AWS_ACCESS_KEY_ID="$ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
export AWS_DEFAULT_REGION="$REGION"

echo "==> Creating bucket s3://${BUCKET}"
if aws s3api head-bucket --bucket "$BUCKET" --endpoint-url "$ENDPOINT" 2>/dev/null; then
  echo "Bucket exists."
else
  aws s3api create-bucket --bucket "$BUCKET" --endpoint-url "$ENDPOINT"
fi

CORS_FILE="$(mktemp)"
trap 'rm -f "$CORS_FILE"' EXIT
cat >"$CORS_FILE" <<'EOF'
{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "HEAD"],
      "AllowedOrigins": ["http://localhost:5173", "http://127.0.0.1:5173"],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF

aws s3api put-bucket-cors \
  --bucket "$BUCKET" \
  --cors-configuration "file://$CORS_FILE" \
  --endpoint-url "$ENDPOINT" 2>/dev/null || true

if command -v mc >/dev/null 2>&1; then
  mc alias set sclocal "$ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" >/dev/null 2>&1 || true
  mc admin config set sclocal api \
    cors_allow_origin="http://localhost:5173,http://127.0.0.1:5173" >/dev/null 2>&1 || true
fi

printf '' | aws s3 cp - "s3://${BUCKET}/deliveries/inbound/" --endpoint-url "$ENDPOINT"

cat >"$ROOT/backend/.env" <<EOF
# Local development — MinIO (S3-compatible). Swap to real AWS after SSO login.
DATABASE_URL=sqlite:///../data/catalog.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
SEED_ON_STARTUP=true

TMDB_API_KEY=your_tmdb_api_key_here

# Local MinIO (S3-compatible)
AWS_ACCESS_KEY_ID=${ACCESS_KEY}
AWS_SECRET_ACCESS_KEY=${SECRET_KEY}
AWS_REGION=${REGION}
AWS_ENDPOINT_URL=${ENDPOINT}

INGEST_S3_BUCKET=${BUCKET}
INGEST_S3_PREFIX=deliveries
ASPERA_DROP_PREFIX=inbound
INGEST_OPERATOR_TOKEN=${TOKEN}
EOF

cat >"$ROOT/frontend/.env.local" <<EOF
VITE_INGEST_OPERATOR_TOKEN=${TOKEN}
EOF

echo ""
echo "Local S3 ready."
echo "  Bucket:   s3://${BUCKET}/deliveries/inbound/"
echo "  Endpoint: ${ENDPOINT}"
echo "  Console:  http://127.0.0.1:9001  (${ACCESS_KEY} / ${SECRET_KEY})"
echo ""
echo "Restart app: ./scripts/dev.sh"
