#!/bin/bash
# cloud-init for the Netflix Open Content transfer runner.
set -euxo pipefail
exec > /var/log/netflix-transfer-cloud-init.log 2>&1

( sleep 7200; shutdown -h now ) &

BOOTSTRAP=s3://stream-catalog-ingest/deliveries/inbound/netflix-opencontent/_relay-bootstrap
dnf install -y python3-pip
python3 -m pip install --quiet 'boto3>=1.34,<2'

aws s3 cp "$BOOTSTRAP/transfer.py" /tmp/transfer.py
aws s3 cp "$BOOTSTRAP/manifest.json" /tmp/manifest.json

set +e
python3 /tmp/transfer.py --manifest /tmp/manifest.json
rc=$?
set -e

aws s3 cp /var/log/netflix-transfer-cloud-init.log "$BOOTSTRAP/cloud-init.log" || true
shutdown -h now
exit "$rc"
