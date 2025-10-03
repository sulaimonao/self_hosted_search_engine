#!/usr/bin/env bash

set -euo pipefail

LOG_DIR=logs
BACKEND_PORT="${BACKEND_PORT:-5050}"
API_URL="${API_URL:-http://127.0.0.1:5050/api/llm/health}"
VENV_PY="${VENV_PY:?VENV_PY is not set}"

mkdir -p "${LOG_DIR}"
echo "▶ Starting API (Flask)…"

port_pids=$(lsof -tiTCP:"${BACKEND_PORT}" -sTCP:LISTEN 2>/dev/null || true)
if [[ -n "${port_pids}" ]]; then
  printf "ℹ️  Backend already listening on port %s (PID(s): %s); skipping launch.\n" "${BACKEND_PORT}" "${port_pids}"
  launched=0
  backend_pid=""
else
  rm -f "${LOG_DIR}/backend.pid"
  PYTHONPATH=.. BACKEND_PORT="${BACKEND_PORT}" nohup "${VENV_PY}" -m backend.app > "${LOG_DIR}/backend.log" 2>&1 &
  backend_pid=$!
  echo "${backend_pid}" > "${LOG_DIR}/backend.pid"
  printf "   PID %s\n" "${backend_pid}"
  launched=1
fi

echo "⏳ Waiting for API…"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "${API_URL}" >/dev/null 2>&1; then
    ready=1
    break
  fi

  if [[ "${launched}" -eq 1 && -n "${backend_pid}" ]] && ! kill -0 "${backend_pid}" >/dev/null 2>&1; then
    echo "❌ Backend exited before becoming healthy." >&2
    if [[ -f "${LOG_DIR}/backend.log" ]]; then
      echo "--- logs/backend.log (last 40 lines) ---" >&2
      tail -n 40 "${LOG_DIR}/backend.log" >&2
      echo "---------------------------------------" >&2
    else
      echo "(logs/backend.log missing)" >&2
    fi
    rm -f "${LOG_DIR}/backend.pid"
    exit 1
  fi

  sleep 0.5
done

if [[ "${ready}" -ne 1 ]]; then
  echo "API not ready" >&2
  if [[ "${launched}" -eq 1 && -f "${LOG_DIR}/backend.log" ]]; then
    echo "--- logs/backend.log (last 40 lines) ---" >&2
    tail -n 40 "${LOG_DIR}/backend.log" >&2
    echo "---------------------------------------" >&2
  fi
  exit 1
fi
