#!/usr/bin/env bash
# Verify cloud API is wired correctly. Usage: ./scripts/verify-cloud.sh https://xxx.awsapprunner.com
set -euo pipefail

API="${1:?Usage: $0 https://your-app-runner-url}"
API="${API%/}"

echo "Health:        $(curl -sf "${API}/health" || echo FAILED)"
echo "Metadata:      $(curl -sf "${API}/api/v1/metadata/health" || echo FAILED)"
echo "Search test:   $(curl -sf "${API}/api/v1/metadata/search?q=gladiator" | head -c 120 || echo FAILED)..."
