"""Utilities for exporting and importing portable workspace bundles."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from backend.app.db import AppStateDB

_BUNDLE_COMPONENTS = ("threads", "messages", "tasks", "browser_history")


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _normalize_components(components: Sequence[str] | None) -> list[str]:
    if not components:
        return list(_BUNDLE_COMPONENTS)
    normalized: list[str] = []
    for entry in components:
        candidate = (entry or "").strip().lower()
        if not candidate:
            continue
        if candidate not in _BUNDLE_COMPONENTS:
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized or list(_BUNDLE_COMPONENTS)


def _write_ndjson(path: Path, records: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def export_bundle(
    state_db: AppStateDB,
    bundle_dir: Path,
    *,
    components: Sequence[str] | None = None,
) -> tuple[Path, dict[str, object]]:
    selected = _normalize_components(components)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "generated_at": _now_iso(),
        "included_components": selected,
    }
    with tempfile.TemporaryDirectory(prefix="bundle-staging-") as tmpdir:
        staging = Path(tmpdir)
        files: dict[str, Path] = {}
        if "threads" in selected:
            data = state_db.export_llm_threads()
            if data:
                path = staging / "threads.ndjson"
                _write_ndjson(path, data)
                files["threads"] = path
        if "messages" in selected:
            data = state_db.export_llm_messages()
            if data:
                path = staging / "messages.ndjson"
                _write_ndjson(path, data)
                files["messages"] = path
        if "tasks" in selected:
            data = state_db.export_tasks()
            if data:
                path = staging / "tasks.ndjson"
                _write_ndjson(path, data)
                files["tasks"] = path
        if "browser_history" in selected:
            data = state_db.export_browser_history()
            if data:
                path = staging / "browser_history.ndjson"
                _write_ndjson(path, data)
                files["browser_history"] = path
        manifest_path = staging / "bundle.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        bundle_name = f"bundle-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%S')}.zip"
        bundle_path = bundle_dir / bundle_name
        with ZipFile(bundle_path, "w", ZIP_DEFLATED) as archive:
            archive.write(manifest_path, arcname="bundle.json")
            for component, file_path in files.items():
                archive.write(file_path, arcname=f"{component}.ndjson")
    return bundle_path, manifest


def import_bundle(
    state_db: AppStateDB,
    bundle_path: Path,
    *,
    components: Sequence[str] | None = None,
) -> dict[str, int]:
    resolved = bundle_path if bundle_path.is_absolute() else bundle_path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(resolved)
    with ZipFile(resolved, "r") as archive:
        try:
            manifest_payload = json.loads(archive.read("bundle.json"))
        except KeyError as exc:  # pragma: no cover - invalid archive
            raise ValueError("bundle missing manifest") from exc
    schema_version = int(manifest_payload.get("schema_version") or 0)
    if schema_version != 1:
        raise ValueError("unsupported bundle schema version")
    included = set(manifest_payload.get("included_components") or [])
    requested = _normalize_components(components)
    target_components = [component for component in requested if component in included]
    stats = {component: 0 for component in _BUNDLE_COMPONENTS}
    with ZipFile(resolved, "r") as archive:
        for component in target_components:
            filename = f"{component}.ndjson"
            if filename not in archive.namelist():
                continue
            with archive.open(filename, "r") as handle:
                for raw_line in handle:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    if component == "threads":
                        state_db.import_llm_thread_record(record)
                    elif component == "messages":
                        state_db.import_llm_message_record(record)
                    elif component == "tasks":
                        state_db.import_task_record(record)
                    elif component == "browser_history":
                        state_db.import_browser_history_record(record)
                    stats[component] += 1
    return stats

