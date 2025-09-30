#!/usr/bin/env bash
set -euo pipefail

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for dev_verify.sh" >&2
  exit 1
fi

printf '== Port listeners ==\n'
lsof -iTCP:3100 -sTCP:LISTEN || true
lsof -iTCP:5050 -sTCP:LISTEN || true

echo
printf '== Backend model inventory ==\n'
curl -sS http://127.0.0.1:5050/api/llm/models | jq .

echo
printf '== Backend LLM health ==\n'
curl -sS http://127.0.0.1:5050/api/llm/health | jq .

echo
printf '[verify] models\n'
curl -s http://127.0.0.1:5050/api/llm/models | jq '.chat_models'

echo
printf '[verify] extract\n'
curl -s -X POST "http://127.0.0.1:5050/api/extract?vision=0" \
  -H 'content-type: application/json' \
  -d '{"url":"https://www.wikidata.org/wiki/Wikidata:Main_Page"}' | jq '.title, (.text|length)'

echo
printf '[verify] chat\n'
curl -s -X POST http://127.0.0.1:5050/api/chat \
  -H 'content-type: application/json' \
  -d '{"model":"gemma3","messages":[{"role":"user","content":"Say hi."}]}' | jq .
