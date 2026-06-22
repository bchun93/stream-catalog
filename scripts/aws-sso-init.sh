#!/usr/bin/env bash
# One-time IAM Identity Center (SSO) profile setup for stream-catalog.
# You will be prompted for SSO start URL, region, account, and role.
set -euo pipefail

PROFILE="${1:-stream-catalog-dev}"

if command -v aws >/dev/null 2>&1; then
  AWS=aws
elif [[ -x "$HOME/.local/bin/aws" ]]; then
  AWS="$HOME/.local/bin/aws"
else
  echo "Install AWS CLI first: uv tool install awscli" >&2
  exit 1
fi

echo "Configuring AWS SSO profile: $PROFILE"
echo "Use values from: AWS Console → IAM Identity Center → Settings"
echo ""

"$AWS" configure sso --profile "$PROFILE"

echo ""
echo "Logging in (browser will open)..."
"$AWS" sso login --profile "$PROFILE"

echo ""
echo "Identity:"
AWS_PROFILE="$PROFILE" "$AWS" sts get-caller-identity

echo ""
echo "Next: ./scripts/setup-aws-s3.sh"
