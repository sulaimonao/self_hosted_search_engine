#!/usr/bin/env bash
set -euo pipefail
URL="${1:-http://127.0.0.1:3100}"
LIMIT="${2:-60}"

for ((i=0; i<LIMIT; i++)); do
  if curl -fsS "$URL" >/dev/null; then
    echo "ready: $URL"
    exit 0
  fi
  sleep 1
done

echo "timeout waiting for $URL"
curl -v "$URL" || true
exit 1
