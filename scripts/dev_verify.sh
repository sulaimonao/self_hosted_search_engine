#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:5050}"
UI_BASE="${UI_BASE:-http://127.0.0.1:3100}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[verify] jq is required (brew install jq)." >&2
  exit 1
fi

printf '[verify] API health %s\n' "$API_BASE/api/llm/health"
curl -sS "$API_BASE/api/llm/health" | jq . > /dev/null

echo "[verify] Frontend root (should be Next.js HTML)"
curl -sS "$UI_BASE" | head -n 2

printf '[verify] Proxy %s\n' "$UI_BASE/api/llm/models"
curl -sS "$UI_BASE/api/llm/models" | jq . > /dev/null

echo "[verify] Done"
