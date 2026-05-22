#!/usr/bin/env bash
# Verify cloud API. Usage: ./scripts/verify-cloud.sh https://your-api.onrender.com
set -euo pipefail

API="${1:?Usage: $0 https://your-api-url}"
API="${API%/}"

echo "Health:     $(curl -sf "${API}/health" || echo FAILED)"
echo "Ready:      $(curl -sf "${API}/ready" || echo FAILED)"
echo "Titles:     $(curl -sf "${API}/api/v1/titles" | head -c 80 || echo FAILED)..."
echo "TMDB:       $(curl -sf "${API}/api/v1/metadata/health" || echo FAILED)"
echo "Search:     $(curl -sS -w ' HTTP %{http_code}' "${API}/api/v1/metadata/search?q=gladiator" | head -c 200 || echo FAILED)"
echo ""
echo "CORS preflight (simulates Amplify browser):"
curl -sf -X OPTIONS "${API}/api/v1/titles" \
  -H "Origin: https://main.amplifyapp.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: content-type" \
  -D - -o /dev/null | grep -i access-control || echo "OPTIONS FAILED"
