"""Ensure the project root is importable during tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("EMBED_TEST_MODE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
