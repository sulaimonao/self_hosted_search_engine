"""Configuration objects for the ``chromadb`` stub."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Mirror the signature of the real ``chromadb.config.Settings``."""

    anonymized_telemetry: bool = False
    allow_reset: bool = True
    is_persistent: bool = True


__all__ = ["Settings"]
