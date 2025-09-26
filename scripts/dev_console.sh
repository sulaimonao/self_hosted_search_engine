#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${1:-python3}"

cd "$ROOT_DIR"

set -a
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi
set +a

INDEX_DIR="${INDEX_DIR:-./data/whoosh}"
CRAWL_STORE="${CRAWL_STORE:-./data/crawl}"
NORMALIZED_PATH="${NORMALIZED_PATH:-./data/normalized/normalized.jsonl}"
CHROMA_PERSIST_DIR="${CHROMA_PERSIST_DIR:-./data/chroma}"
CHROMADB_DISABLE_TELEMETRY="${CHROMADB_DISABLE_TELEMETRY:-1}"
FLASK_RUN_PORT="${UI_PORT:-${FLASK_RUN_PORT:-5000}}"
FLASK_RUN_HOST="${FLASK_RUN_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
NEXT_PUBLIC_BACKEND_URL="${NEXT_PUBLIC_BACKEND_URL:-http://${FLASK_RUN_HOST}:${FLASK_RUN_PORT}}"

export INDEX_DIR CRAWL_STORE NORMALIZED_PATH CHROMA_PERSIST_DIR CHROMADB_DISABLE_TELEMETRY
export FLASK_RUN_PORT FLASK_RUN_HOST NEXT_PUBLIC_BACKEND_URL

"${PYTHON_BIN}" bin/dev_check.py

cleanup() {
  trap - SIGINT SIGTERM EXIT
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    kill "$BACKEND_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    kill "$FRONTEND_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup SIGINT SIGTERM EXIT

"${PYTHON_BIN}" -m flask --app app --debug run &
BACKEND_PID=$!

echo "⚙️  Backend running on http://${FLASK_RUN_HOST}:${FLASK_RUN_PORT}" >&2

npm --prefix frontend run dev -- --hostname 0.0.0.0 --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

echo "🖥️  Frontend running on http://127.0.0.1:${FRONTEND_PORT}" >&2

tail -f /dev/null --pid "$BACKEND_PID" --pid "$FRONTEND_PID" 2>/dev/null || wait -n "$BACKEND_PID" "$FRONTEND_PID"
