#!/usr/bin/env bash
# Configure Amplify + App Runner so production matches local.
# Prerequisites: AWS CLI configured (aws configure), deploy.env filled in.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${DEPLOY_ENV:-$ROOT/deploy.env}"

unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "  cp deploy.env.example deploy.env"
  echo "  # edit with your App Runner URL, Amplify app id, DATABASE_URL, TMDB_API_KEY"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

: "${APP_RUNNER_URL:?Set APP_RUNNER_URL in deploy.env}"
: "${AMPLIFY_APP_ID:?Set AMPLIFY_APP_ID in deploy.env}"
: "${AMPLIFY_BRANCH:=main}"
: "${AWS_REGION:=us-east-1}"
: "${DATABASE_URL:?Set DATABASE_URL in deploy.env}"
: "${TMDB_API_KEY:?Set TMDB_API_KEY in deploy.env}"

export AWS_DEFAULT_REGION="$AWS_REGION"

echo "==> Verifying AWS credentials"
aws sts get-caller-identity

echo "==> Setting Amplify environment variable VITE_API_URL"
aws amplify update-branch \
  --app-id "$AMPLIFY_APP_ID" \
  --branch-name "$AMPLIFY_BRANCH" \
  --environment-variables "VITE_API_URL=${APP_RUNNER_URL}" \
  --no-cli-pager

echo "==> Triggering Amplify rebuild"
JOB_ID=$(aws amplify start-job \
  --app-id "$AMPLIFY_APP_ID" \
  --branch-name "$AMPLIFY_BRANCH" \
  --job-type RELEASE \
  --query 'jobSummary.jobId' \
  --output text)
echo "Amplify job started: $JOB_ID"

echo "==> App Runner: set these in Console → Configuration → Environment variables:"
echo "      DATABASE_URL"
echo "      TMDB_API_KEY"
echo "      SEED_ON_STARTUP=${SEED_ON_STARTUP:-false}"
if [[ -n "${CORS_ORIGINS:-}" ]]; then
  echo "      CORS_ORIGINS=${CORS_ORIGINS}"
fi
echo "    (Amplify *.amplifyapp.com origins are allowed automatically by the API)"

echo ""
echo "==> Verify after deploy completes:"
echo "  curl ${APP_RUNNER_URL}/api/v1/metadata/health"
echo "  Open Amplify URL → sidebar should show API Connected · TMDB ok"
