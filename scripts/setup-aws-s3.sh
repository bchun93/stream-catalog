#!/usr/bin/env bash
# Create S3 bucket + CORS for stream-catalog local/dev use.
# Prereq: AWS CLI authenticated (SSO recommended):
#   aws configure sso --profile stream-catalog-dev
#   aws sso login --profile stream-catalog-dev
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="${AWS_PROFILE:-stream-catalog-dev}"
REGION="${AWS_REGION:-us-east-1}"
BUCKET_PREFIX="${INGEST_S3_BUCKET_PREFIX:-stream-catalog-ingest}"
S3_PREFIX="${INGEST_S3_PREFIX:-deliveries}"
ASPERA_PREFIX="${ASPERA_DROP_PREFIX:-inbound}"

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="$REGION"

aws_cli() {
  if command -v aws >/dev/null 2>&1; then
    aws "$@"
    return
  fi
  if [[ -x "$HOME/.local/bin/aws" ]]; then
    "$HOME/.local/bin/aws" "$@"
    return
  fi
  echo "AWS CLI not found. Install: uv tool install awscli" >&2
  exit 1
}

echo "==> Checking AWS credentials (profile: $PROFILE)"
if ! aws_cli sts get-caller-identity >/dev/null 2>&1; then
  echo "Not logged in. Run:" >&2
  echo "  aws configure sso --profile $PROFILE" >&2
  echo "  aws sso login --profile $PROFILE" >&2
  exit 1
fi

ACCOUNT_ID="$(aws_cli sts get-caller-identity --query Account --output text)"
BUCKET="${INGEST_S3_BUCKET:-${BUCKET_PREFIX}-${ACCOUNT_ID}}"

echo "==> Account: $ACCOUNT_ID"
echo "==> Bucket:  $BUCKET"
echo "==> Region:  $REGION"

if aws_cli s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "Bucket already exists."
else
  echo "==> Creating bucket..."
  if [[ "$REGION" == "us-east-1" ]]; then
    aws_cli s3api create-bucket --bucket "$BUCKET"
  else
    aws_cli s3api create-bucket \
      --bucket "$BUCKET" \
      --create-bucket-configuration "LocationConstraint=$REGION"
  fi
fi

echo "==> Blocking public access (recommended)"
aws_cli s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

CORS_FILE="$(mktemp)"
trap 'rm -f "$CORS_FILE"' EXIT
cat >"$CORS_FILE" <<'EOF'
{
  "CORSRules": [
    {
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "PUT", "HEAD"],
      "AllowedOrigins": [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://*.amplifyapp.com"
      ],
      "ExposeHeaders": ["ETag"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF

echo "==> Applying CORS"
aws_cli s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration "file://$CORS_FILE"

echo "==> Ensuring prefix folders exist"
aws_cli s3api put-object --bucket "$BUCKET" --key "${S3_PREFIX}/" --body /dev/null 2>/dev/null || \
  printf '' | aws_cli s3 cp - "s3://${BUCKET}/${S3_PREFIX}/" 2>/dev/null || true
if [[ -n "$ASPERA_PREFIX" ]]; then
  printf '' | aws_cli s3 cp - "s3://${BUCKET}/${S3_PREFIX}/${ASPERA_PREFIX}/" 2>/dev/null || true
fi

TOKEN="$(openssl rand -hex 24)"
BACKEND_ENV="$ROOT/backend/.env"
FRONTEND_ENV="$ROOT/frontend/.env.local"

if [[ -f "$BACKEND_ENV" ]] && grep -q '^INGEST_OPERATOR_TOKEN=' "$BACKEND_ENV"; then
  TOKEN="$(grep '^INGEST_OPERATOR_TOKEN=' "$BACKEND_ENV" | cut -d= -f2-)"
fi

# Upsert a KEY=value line in an env file without wiping unrelated settings.
upsert_env() {
  local file="$1" key="$2" value="$3"
  local tmp
  tmp="$(mktemp)"
  if [[ -f "$file" ]]; then
    # Drop MinIO endpoint + any prior value for this key (active or commented).
    grep -v -E "^(# )?${key}=" "$file" | grep -v -E '^AWS_ENDPOINT_URL=' >"$tmp" || true
  else
    : >"$tmp"
  fi
  printf '%s=%s\n' "$key" "$value" >>"$tmp"
  mv "$tmp" "$file"
}

echo "==> Updating $BACKEND_ENV for Amazon S3 (preserving other settings)"
if [[ ! -f "$BACKEND_ENV" ]]; then
  cat >"$BACKEND_ENV" <<EOF
# Local development — Amazon S3 (see scripts/setup-aws-s3.sh)
DATABASE_URL=sqlite:///../data/catalog.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
SEED_ON_STARTUP=true
EOF
fi

# Ensure MinIO endpoint is not left active. Only strip static keys when they look
# like the local MinIO placeholders (do not wipe real AWS access keys).
if [[ -f "$BACKEND_ENV" ]]; then
  tmp="$(mktemp)"
  awk '
    BEGIN { FS="="; OFS="=" }
    /^AWS_ENDPOINT_URL=/ { next }
    /^AWS_ACCESS_KEY_ID=streamcatalog$/ { next }
    /^AWS_SECRET_ACCESS_KEY=streamcatalog-dev-secret$/ { next }
    { print }
  ' "$BACKEND_ENV" >"$tmp"
  mv "$tmp" "$BACKEND_ENV"
fi

upsert_env "$BACKEND_ENV" "AWS_PROFILE" "$PROFILE"
upsert_env "$BACKEND_ENV" "AWS_REGION" "$REGION"
upsert_env "$BACKEND_ENV" "INGEST_S3_BUCKET" "$BUCKET"
upsert_env "$BACKEND_ENV" "INGEST_S3_PREFIX" "$S3_PREFIX"
upsert_env "$BACKEND_ENV" "ASPERA_DROP_PREFIX" "$ASPERA_PREFIX"
upsert_env "$BACKEND_ENV" "INGEST_OPERATOR_TOKEN" "$TOKEN"
# Keep analysis bucket aligned with ingest for decision 1A unless already set.
if ! grep -q '^S3_ANALYSIS_BUCKET=' "$BACKEND_ENV"; then
  upsert_env "$BACKEND_ENV" "S3_ANALYSIS_BUCKET" "$BUCKET"
fi

echo "==> Updating $FRONTEND_ENV"
if [[ ! -f "$FRONTEND_ENV" ]]; then
  cat >"$FRONTEND_ENV" <<EOF
# Local dev — Vite proxies /api to localhost:8000
# VITE_API_URL=
EOF
fi
upsert_env "$FRONTEND_ENV" "VITE_INGEST_OPERATOR_TOKEN" "$TOKEN"

echo ""
echo "Done. Upload/Storage now target Amazon S3 (not MinIO)."
echo "  Bucket:  s3://${BUCKET}/${S3_PREFIX}/${ASPERA_PREFIX}/"
echo "  Profile: ${PROFILE}"
echo "  Backend: ${BACKEND_ENV}"
echo "  Frontend:${FRONTEND_ENV}"
echo ""
echo "Restart the API so it picks up .env, then open:"
echo "  Upload:  http://localhost:5173/upload"
echo "  Storage: http://localhost:5173/storage"
