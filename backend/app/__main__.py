"""Command line entry-point for running the Flask API."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from . import create_app

LOGGER = logging.getLogger(__name__)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main() -> None:
    """Create and run the Flask development server."""
    load_dotenv()

    app = create_app()

    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    port = int(os.getenv("BACKEND_PORT", "5050"))
    reload_enabled = _env_flag("BACKEND_RELOAD")

    if reload_enabled:
        LOGGER.info("Starting Flask dev server with auto reload enabled")
    else:
        LOGGER.info("Starting Flask dev server (no auto reload)")

    app.run(host=host, port=port, debug=reload_enabled, use_reloader=reload_enabled)


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
