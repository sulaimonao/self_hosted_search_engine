#!/usr/bin/env bash
set -euo pipefail

echo "[bootstrap] Python venv & deps"
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
pip install -e .

echo "[bootstrap] Node deps"
(cd frontend && npm i)

echo "[bootstrap] Playwright chromium"
. .venv/bin/activate && playwright install chromium || true

echo "[bootstrap] Preflight"
BACKEND_PORT=${BACKEND_PORT:-5050} FRONTEND_PORT=${FRONTEND_PORT:-3100} ./scripts/preflight.sh
echo "[bootstrap] Done"
