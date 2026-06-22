#!/bin/sh
# Render sets PORT at runtime (often 10000). Local/docker default is 8000.
set -e
PORT="${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
