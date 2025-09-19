from __future__ import annotations

import json

from backend.app.pipeline.normalize import normalize


def test_normalize_extracts_body_and_language(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    record = {
        "url": "https://example.com/page",
        "status": 200,
        "html": """
        <html>
          <head><title>Example</title></head>
          <body>
            <h1>Packaging Basics</h1>
            <h2>Overview</h2>
            <p>Building Python packages with modern tooling.</p>
            <script>console.log('ignore me');</script>
          </body>
        </html>
        """,
        "title": "Example",
    }
    with (raw_dir / "sample.jsonl").open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(record))

    output = tmp_path / "normalized.jsonl"
    docs = normalize(raw_dir, output)
    assert docs
    doc = docs[0]
    assert doc["url"] == record["url"]
    assert doc["body"]
    assert "Packaging" in doc["body"]
    assert doc["lang"]
    assert "Packaging Basics" in doc["h1h2"]
    assert output.exists()
