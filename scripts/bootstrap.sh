#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

echo "[bootstrap] Resolving Python interpreter"
PY_CMD="${PY:-python3.11}"
if ! command -v "$PY_CMD" >/dev/null 2>&1; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY_CMD="$candidate"
      break
    fi
  done
fi
if ! command -v "$PY_CMD" >/dev/null 2>&1; then
  echo "[bootstrap] ✖ Unable to locate python3 interpreter (tried python3.11, python3, python)" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[bootstrap] Creating virtualenv at $VENV_DIR with $PY_CMD"
  "$PY_CMD" -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "[bootstrap] Python deps"
pip install -U pip setuptools wheel
if [ -f "$ROOT_DIR/requirements.txt" ]; then
  pip install -r "$ROOT_DIR/requirements.txt"
fi
if [ -f "$ROOT_DIR/requirements-dev.txt" ]; then
  pip install -r "$ROOT_DIR/requirements-dev.txt"
fi
pip install -e "$ROOT_DIR"

echo "[bootstrap] Node deps"
(cd "$ROOT_DIR/frontend" && npm install --no-audit --no-fund)

echo "[bootstrap] Playwright chromium"
playwright install chromium || true

echo "[bootstrap] Preflight"
BACKEND_PORT=${BACKEND_PORT:-5050} FRONTEND_PORT=${FRONTEND_PORT:-3100} "$ROOT_DIR/scripts/preflight.sh"
echo "[bootstrap] Done"
