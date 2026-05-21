#!/usr/bin/env bash
# Configure Amplify to use your cloud API (Render, etc.).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${DEPLOY_ENV:-$ROOT/deploy.env}"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "  cp deploy.env.example deploy.env"
  echo "  # Set API_URL (Render) and AMPLIFY_APP_ID"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${API_URL:?Set API_URL in deploy.env (your Render service URL)}"
: "${AMPLIFY_APP_ID:?Set AMPLIFY_APP_ID in deploy.env}"
: "${AMPLIFY_BRANCH:=main}"
: "${AWS_REGION:=us-east-1}"

export AWS_DEFAULT_REGION="$AWS_REGION"

echo "==> Verifying AWS credentials"
aws sts get-caller-identity

echo "==> Setting Amplify VITE_API_URL=${API_URL}"
aws amplify update-branch \
  --app-id "$AMPLIFY_APP_ID" \
  --branch-name "$AMPLIFY_BRANCH" \
  --environment-variables "VITE_API_URL=${API_URL}" \
  --no-cli-pager

echo "==> Triggering Amplify rebuild"
JOB_ID=$(aws amplify start-job \
  --app-id "$AMPLIFY_APP_ID" \
  --branch-name "$AMPLIFY_BRANCH" \
  --job-type RELEASE \
  --query 'jobSummary.jobId' \
  --output text)
echo "Amplify job started: $JOB_ID"

echo ""
echo "==> API (Render): ensure these env vars are set in Render dashboard:"
echo "      DATABASE_URL, TMDB_API_KEY, SEED_ON_STARTUP=false (after first seed)"
echo ""
echo "==> Verify:"
echo "  ./scripts/verify-cloud.sh ${API_URL}"
echo "  Then open Amplify URL — sidebar should show API Connected"
