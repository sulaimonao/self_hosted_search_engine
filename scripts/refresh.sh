#!/usr/bin/env bash
set -euo pipefail

if [[ ${1:-} == "" ]]; then
  echo "Usage: $0 <seed-id> [base-url]" >&2
  exit 1
fi

SEED_ID="$1"
BASE_URL="${2:-http://127.0.0.1:5050}"
ENDPOINT="${BASE_URL%/}/api/refresh"

read -r -d '' PAYLOAD <<JSON || true
{
  "query": { "seed_ids": ["${SEED_ID}"] },
  "use_llm": false,
  "force": true
}
JSON

RESPONSE=$(curl --silent --show-error --write-out "\n%{http_code}" \
  -H "Content-Type: application/json" \
  -X POST \
  -d "${PAYLOAD}" \
  "${ENDPOINT}")

HTTP_STATUS=$(printf '%s' "${RESPONSE}" | tail -n 1)
BODY=$(printf '%s' "${RESPONSE}" | sed '$d')

printf 'POST %s -> HTTP %s\n' "${ENDPOINT}" "${HTTP_STATUS}"
printf '%s\n' "${BODY}"
