"""Tiny performance smoke test for the agent maintainer loop."""

from __future__ import annotations

import time


def main() -> int:
    start = time.perf_counter()

    # Placeholder workload; replace with real micro-benchmarks when available.
    time.sleep(0.05)

    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms >= 500:
        raise AssertionError(f"perf smoke too slow: {elapsed_ms:.1f} ms")
    print("perf_ok", round(elapsed_ms, 1), "ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
