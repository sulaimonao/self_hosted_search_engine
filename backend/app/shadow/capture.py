"""Shadow snapshot ingestion helpers."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from flask import Flask

from backend.app.config import AppConfig
from backend.app.db import AppStateDB
from backend.app.services.vector_index import VectorIndexService

from .policy_store import ShadowPolicyStore


@dataclass(slots=True)
class SnapshotResult:
    """Lightweight response wrapper returned to API callers."""

    status: int
    payload: dict[str, Any]


class ShadowCaptureService:
    """Process renderer-provided snapshots and persist diagnostics."""

    def __init__(
        self,
        *,
        app: Flask,
        policy_store: ShadowPolicyStore,
        vector_index: VectorIndexService,
        config: AppConfig,
        state_db: AppStateDB,
    ) -> None:
        self._app = app
        self._policy_store = policy_store
        self._vector_index = vector_index
        self._config = config
        self._state_db = state_db
        self._snapshot_dir = (config.agent_data_dir / "documents" / "shadow" / "snapshots").resolve()
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    def process_snapshot(self, payload: Mapping[str, Any]) -> SnapshotResult:
        if not isinstance(payload, Mapping):
            return SnapshotResult(400, {"error": "invalid_payload"})

        raw_url = str(payload.get("url") or "").strip()
        if not raw_url:
            return SnapshotResult(400, {"error": "url_required"})

        parsed = urlparse(raw_url)
        domain = (parsed.hostname or "").lower()
        policy = self._policy_store.get_domain(domain) if domain else self._policy_store.get_global()

        observed_at = time.time()
        document_id = uuid.uuid4().hex
        document = {
            "id": document_id,
            "url": raw_url,
            "canonical_url": raw_url,
            "domain": domain,
            "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)),
        }

        record = {
            "document": document,
            "policy": policy.to_dict(),
            "received_at": observed_at,
            "session_id": payload.get("session_id") or payload.get("sessionId"),
            "tab_id": payload.get("tab_id") or payload.get("tabId"),
            "outlinks": payload.get("outlinks"),
        }

        self._persist_record(document_id, record)

        response = {
            "ok": True,
            "policy": policy.to_dict(),
            "document": document,
            "artifacts": [],
            "rag_indexed": False,
            "pending_embedding": False,
            "token_count": None,
            "bytes": None,
            "training_record": None,
        }

        return SnapshotResult(200, response)

    def _persist_record(self, document_id: str, record: Mapping[str, Any]) -> None:
        target = self._snapshot_dir / f"{document_id}.json"
        try:
            target.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except OSError:
            # Disk persistence is best-effort; log but continue.
            self._app.logger.debug("shadow.capture.persist_failed", exc_info=True)

