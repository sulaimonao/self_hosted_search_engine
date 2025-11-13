"""Shadow snapshot ingestion helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

import requests
from flask import Flask

try:  # pragma: no cover - optional dependency guard
    from bs4 import BeautifulSoup  # type: ignore[import]
except ImportError:  # pragma: no cover - fallback parser
    BeautifulSoup = None

from backend.app.config import AppConfig
from backend.app.db import AppStateDB
from backend.app.pipeline.normalize import (
    _collect_headings,
    _detect_language,
    _extract_text,
)
from backend.app.services.vector_index import (
    EmbedderUnavailableError,
    VectorIndexService,
)

from .policy_store import ShadowPolicyStore


LOGGER = logging.getLogger(__name__)
_DEFAULT_HEADERS = {"User-Agent": "SelfHostedShadowCapture/1.0"}


def _extract_title(html: str) -> str:
    if not html:
        return ""
    if BeautifulSoup is not None:
        try:
            soup = BeautifulSoup(html, "lxml")
            title_tag = soup.find("title")
            if title_tag is not None:
                title_text = title_tag.get_text(" ", strip=True)
                if title_text:
                    return title_text
        except Exception:  # pragma: no cover - defensive guard
            LOGGER.debug(
                "failed to parse <title> tag with BeautifulSoup", exc_info=True
            )
    match = re.search(
        r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL
    )
    if match:
        candidate = re.sub(r"\s+", " ", match.group(1)).strip()
        if candidate:
            return candidate
    return ""


def _compose_markdown(title: str, headings: str, body: str) -> str:
    sections: list[str] = []
    title_text = title.strip()
    if title_text:
        sections.append(f"# {title_text}")
    headings_text = headings.strip()
    if headings_text:
        sections.append(headings_text)
    body_text = body.strip()
    if body_text:
        sections.append(body_text)
    return "\n\n".join(sections).strip()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


@dataclass(slots=True)
class SnapshotResult:
    """Lightweight response wrapper returned to API callers."""

    status: int
    payload: dict[str, Any]

    @property
    def ok(self) -> bool:
        payload_flag = self.payload.get("ok")
        if isinstance(payload_flag, bool):
            return payload_flag
        return 200 <= int(self.status) < 400


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
        self._snapshot_dir = (
            config.agent_data_dir / "documents" / "shadow" / "snapshots"
        ).resolve()
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    def process_snapshot(self, payload: Mapping[str, Any]) -> SnapshotResult:
        if not isinstance(payload, Mapping):
            return SnapshotResult(400, {"error": "invalid_payload"})

        raw_url = str(payload.get("url") or "").strip()
        if not raw_url:
            return SnapshotResult(400, {"error": "url_required"})

        parsed = urlparse(raw_url)
        domain = (parsed.hostname or "").lower()
        policy = (
            self._policy_store.get_domain(domain)
            if domain
            else self._policy_store.get_global()
        )

        observed_at = time.time()
        document_id = uuid.uuid4().hex
        document = {
            "id": document_id,
            "url": raw_url,
            "canonical_url": raw_url,
            "domain": domain,
            "observed_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(observed_at)
            ),
        }
        record: dict[str, Any] = {
            "document": document,
            "policy": policy.to_dict(),
            "received_at": observed_at,
            "session_id": payload.get("session_id") or payload.get("sessionId"),
            "tab_id": payload.get("tab_id") or payload.get("tabId"),
            "outlinks": payload.get("outlinks"),
        }

        base_documents_dir = (self._config.agent_data_dir / "documents").resolve()
        domain_segment = domain or (parsed.hostname or "")
        safe_domain = re.sub(r"[^a-z0-9.-]", "-", domain_segment.lower()).strip("-")
        if not safe_domain:
            safe_domain = "unknown"
        snapshot_dir = (self._snapshot_dir / safe_domain / document_id).resolve()
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        record["snapshot_dir"] = str(snapshot_dir)

        try:
            http_resp = requests.get(
                raw_url,
                headers=_DEFAULT_HEADERS,
                timeout=30,
            )
        except requests.RequestException as exc:
            record["error"] = str(exc)
            self._persist_record(document_id, record)
            return SnapshotResult(
                502,
                {
                    "ok": False,
                    "error": "capture_failed",
                    "message": str(exc),
                    "policy": policy.to_dict(),
                    "document": document,
                },
            )

        try:
            status_code = int(http_resp.status_code)
        except Exception:  # pragma: no cover - defensive guard
            status_code = 0
        html = http_resp.text or ""
        raw_bytes = (
            len(http_resp.content)
            if getattr(http_resp, "content", None) is not None
            else len(html.encode("utf-8"))
        )
        with suppress(Exception):
            http_resp.close()
        record["status_code"] = status_code
        record["bytes"] = raw_bytes

        if status_code >= 400 or not html.strip():
            record["error"] = "empty_response" if not html.strip() else "http_error"
            self._persist_record(document_id, record)
            error_payload: dict[str, Any] = {
                "ok": False,
                "error": "snapshot_failed",
                "status": status_code,
                "policy": policy.to_dict(),
                "document": document,
            }
            if not html.strip():
                error_payload["message"] = "empty_response"
            return SnapshotResult(
                status_code if status_code >= 400 else 502, error_payload
            )

        title = _extract_title(html) or (domain or raw_url)
        body = _extract_text(html)
        if not body.strip():
            body = html.strip()
        headings = _collect_headings(html)
        lang = _detect_language(body)
        content_hash = hashlib.sha256(body.encode("utf-8", errors="ignore")).hexdigest()
        markdown = _compose_markdown(title, headings, body)

        normalized_doc = {
            "url": raw_url,
            "canonical_url": raw_url,
            "title": title,
            "h1h2": headings,
            "body": body,
            "lang": lang,
            "fetched_at": observed_at,
            "content_hash": content_hash,
            "outlinks": [],
            "domain": domain,
            "text_markdown": markdown,
        }
        normalized_json = json.dumps(normalized_doc, ensure_ascii=False)

        raw_path = snapshot_dir / "raw.html"
        raw_path.write_text(html, encoding="utf-8")
        normalized_path = snapshot_dir / "normalized.json"
        normalized_payload = normalized_json + "\n"
        normalized_path.write_text(normalized_payload, encoding="utf-8")

        artifacts = [
            {
                "kind": "html",
                "path": str(raw_path.relative_to(base_documents_dir)),
                "bytes": raw_bytes,
                "mime": "text/html",
            },
            {
                "kind": "normalized",
                "path": str(normalized_path.relative_to(base_documents_dir)),
                "bytes": len(normalized_payload.encode("utf-8")),
                "mime": "application/json",
            },
        ]

        training_dir = (self._config.agent_data_dir / "staging" / "training").resolve()
        training_dir.mkdir(parents=True, exist_ok=True)
        training_path = training_dir / f"{document_id}.jsonl"
        training_record = {
            "id": document_id,
            "url": raw_url,
            "title": title,
            "domain": domain,
            "text_markdown": markdown,
            "captured_at": document["observed_at"],
        }
        training_line = json.dumps(training_record, ensure_ascii=False)
        training_path.write_text(training_line + "\n", encoding="utf-8")
        training_payload = {
            "path": str(training_path.relative_to(self._config.agent_data_dir))
        }

        token_count = _estimate_tokens(body)
        description = headings.strip() or body[:280]

        rag_indexed = False
        pending_embedding = False
        rag_error: str | None = None
        try:
            index_result = self._vector_index.upsert_document(
                text=body,
                url=raw_url,
                title=title,
                metadata={
                    "source": "shadow-capture",
                    "domain": domain,
                    "document_id": document_id,
                },
            )
        except EmbedderUnavailableError as exc:
            pending_embedding = True
            rag_error = str(exc)
        except Exception as exc:  # pragma: no cover - defensive guard
            rag_error = str(exc)
            LOGGER.exception("shadow capture indexing failed for %s", raw_url)
        else:
            rag_indexed = (
                bool(index_result.chunks) and not index_result.pending_embedding
            )
            pending_embedding = bool(index_result.pending_embedding)

        normalized_rel_path = str(
            normalized_path.relative_to(self._config.agent_data_dir)
        )
        try:
            self._state_db.upsert_document(
                job_id=None,
                document_id=document_id,
                url=raw_url,
                canonical_url=raw_url,
                site=domain or parsed.hostname or None,
                title=title,
                description=description,
                language=lang,
                fetched_at=observed_at,
                normalized_path=normalized_rel_path,
                text_len=len(body),
                tokens=token_count,
                content_hash=content_hash,
                categories=None,
                labels=None,
                source="shadow-capture",
                verification={"policy_id": policy.policy_id},
            )
        except Exception:  # pragma: no cover - defensive guard
            LOGGER.exception(
                "failed to persist shadow capture document in state DB for %s", raw_url
            )

        document["title"] = title
        record.update(
            {
                "artifacts": artifacts,
                "normalized": normalized_doc,
                "normalized_path": normalized_rel_path,
                "training_record": training_payload,
                "rag_indexed": rag_indexed,
                "pending_embedding": pending_embedding,
                "token_count": token_count,
            }
        )
        if rag_error:
            record["rag_error"] = rag_error
        self._persist_record(document_id, record)

        response: dict[str, Any] = {
            "ok": True,
            "policy": policy.to_dict(),
            "document": document,
            "artifacts": artifacts,
            "rag_indexed": rag_indexed,
            "pending_embedding": pending_embedding,
            "token_count": token_count,
            "bytes": raw_bytes,
            "training_record": training_payload,
        }
        if rag_error:
            response["rag_error"] = rag_error

        return SnapshotResult(201, response)

    def _persist_record(self, document_id: str, record: Mapping[str, Any]) -> None:
        target = self._snapshot_dir / f"{document_id}.json"
        try:
            target.write_text(json.dumps(record, indent=2), encoding="utf-8")
        except OSError:
            # Disk persistence is best-effort; log but continue.
            self._app.logger.debug("shadow.capture.persist_failed", exc_info=True)
