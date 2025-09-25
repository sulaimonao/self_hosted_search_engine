"""Lightweight logging helpers used by server components."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger with a consistent namespace."""
    return logging.getLogger(name)


__all__ = ["get_logger"]
