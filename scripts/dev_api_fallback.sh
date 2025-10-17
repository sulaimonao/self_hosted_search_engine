#!/usr/bin/env bash
set -euo pipefail

# Ensure we reuse the virtualenv interpreter when available so required
# dependencies (e.g. flask-cors) are present.
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  PYTHON_BIN="$(command -v python)"
fi

export PYTHONPATH="${PYTHONPATH:-.}"
export BACKEND_PORT="${BACKEND_PORT:-5050}"

exec "$PYTHON_BIN" -m backend.app
