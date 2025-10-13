#!/usr/bin/env python3
"""Return 'true' if system_check response contains critical failures, else 'false'."""
from __future__ import annotations

import json
import sys


def load_payload() -> str:
    if not sys.stdin.isatty():
        data = sys.stdin.read()
        if data:
            return data
    return sys.argv[1] if len(sys.argv) > 1 else "{}"


def main() -> None:
    raw = load_payload()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print("false")
        return

    summary = payload.get("summary") or {}
    print("true" if summary.get("critical_failures") else "false")


if __name__ == "__main__":
    main()
