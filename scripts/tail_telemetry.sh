#!/usr/bin/env bash
set -euo pipefail
mkdir -p data/telemetry
exec tail -f data/telemetry/events.ndjson
