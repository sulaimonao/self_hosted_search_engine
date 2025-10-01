#!/usr/bin/env bash
set -euo pipefail

PY_OK=$(python3.11 -V >/dev/null 2>&1 && echo yes || echo no)
NODE_V=$(node -v 2>/dev/null || echo "none")
echo "[preflight] python3.11: $PY_OK, node: $NODE_V"

echo "[preflight] ports"
for p in 3100 5050 11434; do
  if lsof -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
    echo "  - port $p is LISTENING"
  else
    echo "  - port $p is free"
  fi
done

echo "[preflight] Ollama"
if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "  - reachable"
else
  echo "  - NOT reachable (start with 'ollama serve' in another terminal)"; exit 1
fi

echo "[preflight] Backend health (if running)"
curl -fsS http://127.0.0.1:${BACKEND_PORT:-5050}/api/llm/health >/dev/null || echo "  - backend not up yet (ok)"

echo "[preflight] Next.js rewrite sanity (if frontend running)"
curl -fsS http://127.0.0.1:${FRONTEND_PORT:-3100}/api/llm/models >/dev/null || echo "  - frontend not up yet (ok)"

echo "[preflight] Playwright chromium install check"
if [ -d "./backend" ]; then
  python3.11 - <<'PY' || true
import sys, subprocess; subprocess.run(["playwright","install","chromium"], check=False)
print("[preflight] playwright install attempted")
PY
fi

echo "[preflight] OK"
