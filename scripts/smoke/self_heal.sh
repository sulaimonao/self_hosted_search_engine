#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SELF_HEAL_BASE_URL:-http://127.0.0.1:5000}"

schema_url="${BASE_URL%/}/api/self_heal/schema"
plan_url="${BASE_URL%/}/api/self_heal?variant=lite"
headless_url="${BASE_URL%/}/api/self_heal/execute_headless"

curl -sS -m 5 -f "$schema_url" > /dev/null

incident_payload='{"id":"smoke","url":"https://example.com/smoke","symptoms":{"bannerText":"Smoke test"}}'
curl -sS -m 8 -f -H "Content-Type: application/json" -X POST "$plan_url" -d "$incident_payload" > /dev/null

headless_status=$(
  curl -sS -m 5 -o /dev/null -w "%{http_code}" \
    -H "Content-Type: application/json" \
    -X POST "$headless_url" \
    -d '{"directive":{"steps":[{"type":"reload"}]},"consent":false}'
)

if [[ "$headless_status" != "400" && "$headless_status" != "200" ]]; then
  echo "unexpected status from headless endpoint: $headless_status" >&2
  exit 1
fi

echo "✅ self-heal smoke passed against ${BASE_URL}"
