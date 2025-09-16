#!/usr/bin/env bash
set -euo pipefail

PY_BIN="${1:-python3}"

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "error: python executable '$PY_BIN' not found" >&2
  exit 1
fi

VERSION="$($PY_BIN -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
MAJOR_MINOR="${VERSION%.*}"
if [[ "${MAJOR_MINOR}" != 3.11* ]]; then
  echo "error: python 3.11 is required, but $PY_BIN reports $VERSION" >&2
  exit 1
fi

echo "$PY_BIN -> Python $VERSION"
