"""Minimal logging bootstrap for backend tests."""

from __future__ import annotations

import logging
import os
from pathlib import Path


_LOG_CONFIGURED = False


def setup_logging() -> None:
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    log_dir = Path(os.getenv("LOG_DIR", "data/logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _LOG_CONFIGURED = True


__all__ = ["setup_logging"]
