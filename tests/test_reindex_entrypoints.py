from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "invocation",
    (
        [sys.executable, "-m", "bin.reindex_incremental"],
        [sys.executable, "bin/reindex_incremental.py"],
    ),
)
def test_incremental_reindex_entrypoints(tmp_path: Path, invocation: list[str]) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    normalized = data_dir / "normalized.jsonl"
    payload = {
        "url": "https://example.com/",
        "lang": "en",
        "title": "Example",
        "h1h2": "Example heading",
        "body": "Example body text",
        "content_hash": "abc123",
        "fetched_at": time.time(),
        "outlinks": ["https://example.org/"],
    }
    normalized.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "DATA_DIR": str(data_dir),
        "INDEX_INC_WINDOW_MIN": "120",
    })

    result = subprocess.run(
        invocation,
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    index_dir = Path(env["DATA_DIR"]) / "index"
    assert index_dir.exists(), f"index directory missing\nstdout={result.stdout}\nstderr={result.stderr}"
