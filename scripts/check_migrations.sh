#!/usr/bin/env bash
set -euo pipefail

TMPDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

export DATA_DIR="$TMPDIR/data"
mkdir -p "$DATA_DIR"

python - <<'PY'
import json
import os
from pathlib import Path

from backend.app import create_app

# Ensure the data directory exists before initialising the app configuration.
Path(os.environ["DATA_DIR"]).mkdir(parents=True, exist_ok=True)

app = create_app()
app.testing = True
with app.test_client() as client:
    response = client.get("/api/diag/db")
    payload = response.get_json()
    if response.status_code != 200 or not payload.get("ok"):
        raise SystemExit(
            f"schema diagnostics failed: {json.dumps(payload, indent=2, sort_keys=True)}"
        )
print("schema diagnostics ok")
PY
