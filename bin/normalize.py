#!/usr/bin/env python3
"""Normalize raw crawl output using the application pipeline."""

from __future__ import annotations

import sys

from backend.app.config import AppConfig
from backend.app.pipeline.normalize import normalize


def main() -> None:
    config = AppConfig.from_env()
    config.ensure_dirs()
    docs = normalize(config.crawl_raw_dir, config.normalized_path)
    print(f"Normalized {len(docs)} document(s) -> {config.normalized_path}")


if __name__ == "__main__":
    sys.exit(main())
