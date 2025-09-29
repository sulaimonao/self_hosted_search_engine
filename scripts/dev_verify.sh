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
printf '== Ollama tags ==\n'
curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name' | grep -E 'gpt-oss|gemma3|embeddinggemma'

echo
printf '== Backend model inventory ==\n'
curl -sS http://127.0.0.1:5050/api/llm/models | jq .

echo
printf '== Backend LLM status ==\n'
curl -sS http://127.0.0.1:5050/api/llm/status | jq .

echo
printf '== Embedder status ==\n'
curl -sS http://127.0.0.1:5050/api/embedder/status | jq .

echo
printf '== CORS preflight (Origin: http://127.0.0.1:3100) ==\n'
curl -i -H "Origin: http://127.0.0.1:3100" http://127.0.0.1:5050/api/llm/status

echo
printf '== Crawl endpoint (colon in path) ==\n'
curl -sS -X POST http://127.0.0.1:5050/api/crawl \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.wikidata.org/wiki/Wikidata:Main_Page","depth":1}'
