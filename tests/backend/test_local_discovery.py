from __future__ import annotations

import json

from backend.app.services.local_discovery import LocalDiscoveryService


def test_local_discovery_processing_and_confirmation(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    ledger_path = tmp_path / "ledger.json"

    path = downloads / "example.txt"

    service = LocalDiscoveryService([downloads], ledger_path)
    try:
        path.write_text("hello world", encoding="utf-8")

        assert service._process_path(path)  # type: ignore[attr-defined]

        pending = service.list_pending()
        assert len(pending) == 1
        record = pending[0]
        assert record.path == str(path)
        assert "hello world" in record.text

        assert service.confirm(record.id, action="included")
    finally:
        service.stop()

    assert ledger_path.exists()
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    key = str(path)
    assert key in payload["paths"]

    # Confirmed files are ignored when the service is reloaded.
    service2 = LocalDiscoveryService([downloads], ledger_path)
    try:
        path.write_text("hello world", encoding="utf-8")
        assert not service2._process_path(path)  # type: ignore[attr-defined]
    finally:
        service2.stop()
