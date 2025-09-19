"""Entry point exposing the Flask application."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

from backend.app import create_app

load_dotenv()

app = create_app()


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app.run(debug=True)
