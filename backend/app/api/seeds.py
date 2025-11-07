"""REST API for managing the seed registry."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

import yaml
from flask import Blueprint, Response, current_app, jsonify, request

LOGGER = logging.getLogger(__name__)

bp = Blueprint("seeds", __name__, url_prefix="/api/seeds")

ALLOWED_SCOPES = {"page", "domain", "allowed-list", "custom"}
DEFAULT_SCOPE = "page"
_ID_SLUG = re.compile(r"[^a-z0-9]+")
_LOCK = threading.Lock()


def _registry_path() -> Path:
    path_value = current_app.config.get("SEED_REGISTRY_PATH")
    if isinstance(path_value, Path):
        return path_value
    if isinstance(path_value, str):
        return Path(path_value)
    package_root = Path(__file__).resolve().parents[2]
    return package_root / "seeds" / "registry.yaml"


def _workspace_directory() -> str:
    directory = current_app.config.get("SEED_WORKSPACE_DIRECTORY")
    if isinstance(directory, str) and directory.strip():
        return directory.strip()
    return "workspace"


def _read_registry() -> tuple[dict[str, Any], str]:
    path = _registry_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        LOGGER.info("seed registry missing at %s; creating default", path)
        raw = b""
    if not raw:
        data: dict[str, Any] = {"version": 1, "crawl_defaults": {}, "directories": {}}
        revision = hashlib.sha256(b"{}").hexdigest()
        return data, revision
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        LOGGER.error("invalid registry yaml: %s", exc)
        raise ValueError("Seed registry is not valid YAML") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Seed registry must be a mapping")
    revision = hashlib.sha256(raw).hexdigest()
    parsed.setdefault("directories", {})
    parsed.setdefault("crawl_defaults", {})
    parsed.setdefault("version", 1)
    return parsed, revision


def _serialize_seed(directory: str, raw: dict[str, Any]) -> dict[str, Any]:
    entrypoints = raw.get("entrypoints")
    if isinstance(entrypoints, str):
        entrypoints = [entrypoints]
    elif not isinstance(entrypoints, list):
        entrypoints = []
    urls = [str(url).strip() for url in entrypoints if isinstance(url, str) and url.strip()]
    seed_id = raw.get("id")
    scope = raw.get("scope") or raw.get("scope_hint") or DEFAULT_SCOPE
    if scope not in ALLOWED_SCOPES:
        scope = DEFAULT_SCOPE
    notes = raw.get("notes")
    if not isinstance(notes, str) or not notes.strip():
        title = raw.get("title")
        # Fallback to title if notes are not provided
        notes = str(title).strip() if isinstance(title, str) and title.strip() else None
    payload = {
        "id": seed_id,
        "directory": directory,
        "entrypoints": urls,
        "url": urls[0] if urls else None,
        "scope": scope,
        "notes": notes,
        "editable": directory == _workspace_directory(),
    }
    created_at = raw.get("created_at")
    if isinstance(created_at, str):
        payload["created_at"] = created_at
    updated_at = raw.get("updated_at")
    if isinstance(updated_at, str):
        payload["updated_at"] = updated_at
    extras = raw.get("extras")
    if isinstance(extras, dict):
        payload["extras"] = extras
    return payload


def _collect_seeds(registry: dict[str, Any]) -> list[dict[str, Any]]:
    directories = registry.get("directories")
    if not isinstance(directories, dict):
        return []
    results: list[dict[str, Any]] = []
    for directory, payload in directories.items():
        sources = payload.get("sources") if isinstance(payload, dict) else None
        if not isinstance(sources, list):
            continue
        for raw in sources:
            if isinstance(raw, dict) and raw.get("id"):
                results.append(_serialize_seed(directory, raw))
    return results


def _write_registry(registry: dict[str, Any]) -> str:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(registry, sort_keys=False, allow_unicode=True)
    tmp_path = Path(f"{path}.tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_path, path)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_entrypoints(
    raw_urls: Iterable[Any],
) -> tuple[list[str], list[dict[str, str]]]:
    validated: list[str] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_url in raw_urls:
        if not isinstance(raw_url, str) or not raw_url.strip():
            continue
        url = raw_url.strip()
        if url in seen:
            continue
        try:
            parsed = parse_http_url(url)
            normalized = urlunparse(
                (parsed.scheme, parsed.netloc, parsed.path or "", "", parsed.query, "")
            )
            validated.append(normalized)
            seen.add(url)
            seen.add(normalized)
        except ValueError as exc:
            errors.append({"url": url, "error": str(exc)})
    return validated, errors


_HTTP_SCHEMES = {"http", "https"}


def parse_http_url(url: str):
    candidate = (url or "").strip()
    if not candidate:
        raise ValueError("URL is required")
    try:
        parsed = urlparse(candidate)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"URL is not valid: {exc}") from exc
    if parsed.scheme not in _HTTP_SCHEMES or not parsed.netloc:
        raise ValueError("Provide an absolute http(s) URL")
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ValueError("URL may not include embedded credentials")
    return parsed


def is_safe_http_url(url: str) -> bool:
    try:
        parse_http_url(url)
    except ValueError:
        return False
    return True


def _normalize_url(url: str) -> str:
    parsed = parse_http_url(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path or "", "", parsed.query, ""))
    return normalized.rstrip("/")


def _urls_equal(a: str, b: str) -> bool:
    return a.rstrip("/").lower() == b.rstrip("/").lower()


def _ensure_workspace(registry: dict[str, Any]) -> list[dict[str, Any]]:
    directories = registry.setdefault("directories", {})
    if not isinstance(directories, dict):
        raise ValueError("Invalid directories block in registry")
    workspace = directories.setdefault(_workspace_directory(), {})
    if not isinstance(workspace, dict):
        raise ValueError("Workspace directory is not a mapping")
    workspace.setdefault(
        "description",
        "Workspace-managed seeds queued through the web UI.",
    )
    defaults = workspace.setdefault("defaults", {})
    if isinstance(defaults, dict):
        defaults.setdefault("kind", "custom")
        defaults.setdefault("strategy", "crawl")
        defaults.setdefault("trust", "medium")
    sources = workspace.setdefault("sources", [])
    if not isinstance(sources, list):
        raise ValueError("Workspace sources must be a list")
    return sources


def _existing_ids(sources: Iterable[dict[str, Any]]) -> set[str]:
    ids: set[str] = set()
    for source in sources:
        identifier = source.get("id")
        if isinstance(identifier, str):
            ids.add(identifier)
    return ids


def _generate_id(url: str, existing: set[str]) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    base = _ID_SLUG.sub("-", host).strip("-") or "seed"
    candidate = f"workspace-{base}"
    suffix = 1
    while candidate in existing:
        suffix += 1
        candidate = f"workspace-{base}-{suffix}"
        if suffix > 50:
            candidate = f"workspace-{uuid.uuid4().hex[:12]}"
            break
    return candidate


def _conflict_response(message: str, revision: str) -> Response:
    return (
        jsonify({"error": message, "revision": revision}),
        409,
    )


def _error_response(message: str, status: int = 400) -> Response:
    return jsonify({"error": message}), status


def _success_payload(registry: dict[str, Any], revision: str) -> Response:
    seeds = _collect_seeds(registry)
    return jsonify({"revision": revision, "seeds": seeds})


@bp.get("")
def get_seeds():
    """Return all seeds from the registry."""
    try:
        registry, _ = _read_registry()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 500
    results = _collect_seeds(registry)
    return jsonify({"ok": True, "data": results})


@bp.post("")
def create_seed():
    """Create a new seed."""
    payload = request.get_json(silent=True) or {}
    raw_entrypoints = payload.get("entrypoints")
    if not isinstance(raw_entrypoints, list):
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            return jsonify({"error": "entrypoints or url is required"}), 400
        raw_entrypoints = [url]

    entrypoints, errors = _validate_entrypoints(raw_entrypoints)
    if not entrypoints:
        return (
            jsonify(
                {
                    "error": "at least one valid entrypoint is required",
                    "detail": errors,
                }
            ),
            400,
        )

    scope = payload.get("scope") or DEFAULT_SCOPE
    if scope not in ALLOWED_SCOPES:
        scope = DEFAULT_SCOPE
    notes = payload.get("notes")

    with _LOCK:
        registry, _ = _read_registry()
        workspace = _workspace_directory()
        if workspace not in registry["directories"]:
            registry["directories"][workspace] = {"sources": []}
        new_entry = _create_seed_entry(entrypoints, scope, notes)
        registry["directories"][workspace]["sources"].insert(0, new_entry)
        _write_registry(registry)

    response_payload = {
        "ok": True,
        "data": _serialize_seed(workspace, new_entry),
    }
    if errors:
        response_payload["errors"] = errors
    return jsonify(response_payload), 201


def _create_seed_entry(
    entrypoints: list[str], scope: str, notes: str | None
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": _generate_seed_id(entrypoints[0]),
        "entrypoints": entrypoints,
        "scope": scope,
        "notes": notes.strip() if notes else None,
        "created_at": now,
        "updated_at": now,
    }


def _generate_seed_id(url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


@bp.put("/<seed_id>")
def update_seed(seed_id: str) -> Response:
    payload = request.get_json(silent=True) or {}
    revision = payload.get("revision")
    if not isinstance(revision, str):
        return _error_response("revision is required")
    with _LOCK:
        registry, current_revision = _read_registry()
        if revision != current_revision:
            return _conflict_response("Seed registry has been modified", current_revision)
        sources = _ensure_workspace(registry)
        target = None
        for source in sources:
            if source.get("id") == seed_id:
                target = source
                break
        if target is None:
            return _error_response("Seed not found", 404)
        new_entrypoints = payload.get("entrypoints")
        if isinstance(new_entrypoints, list):
            validated_urls, validation_errors = _validate_entrypoints(new_entrypoints)
            if validated_urls:
                target["entrypoints"] = validated_urls
                changed = True

        new_scope = payload.get("scope")
        if isinstance(new_scope, str) and new_scope in ALLOWED_SCOPES:
            target["scope"] = new_scope
            changed = True

        new_notes = payload.get("notes")
        if isinstance(new_notes, str):
            target["notes"] = new_notes.strip()
            changed = True

        if changed:
            target["updated_at"] = datetime.now(timezone.utc).isoformat()
            _write_registry(registry)

        directory = next(
            (
                directory
                for directory, dir_payload in registry.get("directories", {}).items()
                if any(
                    isinstance(s, dict) and s.get("id") == seed_id
                    for s in (
                        dir_payload.get("sources", [])
                        if isinstance(dir_payload, dict)
                        else []
                    )
                )
            ),
            "unknown",
        )
        response_payload = {
            "ok": True,
            "data": _serialize_seed(directory, target),
        }
        if "validation_errors" in locals() and validation_errors:
            response_payload["errors"] = validation_errors
        return jsonify(response_payload)


@bp.delete("/<seed_id>")
def delete_seed(seed_id: str):
    payload = request.get_json(silent=True) or {}
    revision = payload.get("revision")
    if not isinstance(revision, str):
        return _error_response("revision is required")
    with _LOCK:
        registry, current_revision = _read_registry()
        if revision != current_revision:
            return _conflict_response("Seed registry has been modified", current_revision)
        sources = _ensure_workspace(registry)
        initial_length = len(sources)
        sources[:] = [source for source in sources if source.get("id") != seed_id]
        if len(sources) == initial_length:
            return _error_response("Seed not found", 404)
        new_revision = _write_registry(registry)
        LOGGER.info("seed %s removed", seed_id)
        return _success_payload(registry, new_revision)


__all__ = ["bp"]
