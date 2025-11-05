#!/usr/bin/env bash
set -euo pipefail

# One-command smoke test for local development.
# Starts backend + frontend, waits for readiness, then runs Playwright smoke tests.

ROOT=$(cd "$(dirname "$0")/.." && pwd -P)
cd "$ROOT"

# Start backend API (ports and envs match repo conventions)
BACKEND_PORT=5050
export BACKEND_PORT

./scripts/dev_api_fallback.sh &
API_PID=$!

# Start frontend dev server
npm --prefix frontend run dev:web &
FRONTEND_PID=$!

# Ensure we kill background processes on exit
cleanup() {
  echo "Cleaning up..."
  kill "$API_PID" || true
  kill "$FRONTEND_PID" || true
}
trap cleanup EXIT

# Wait for services to be ready: web on 3100 and api on 5050
npx wait-on http://127.0.0.1:3100 tcp:5050

# Run playwright smoke tests (use the DEV playwright config which doesn't start webServer)
PLAYWRIGHT_APP_URL=http://127.0.0.1:3100 npm --prefix frontend run test:render-loop:dev

# If tests passed, exit successfully (cleanup will run)
