"""Shadow policy persistence and domain overrides."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Mapping


def _coerce_bool(value: Any, default: bool = False) -> bool:
    """Best-effort coercion for boolean-like payloads."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result


@dataclass(slots=True, frozen=True)
class RateLimit:
    """Lightweight rate-limit configuration for crawls."""

    concurrency: int = 2
    delay_ms: int = 250

    def to_dict(self) -> Dict[str, int]:
        return {"concurrency": max(1, int(self.concurrency)), "delay_ms": max(0, int(self.delay_ms))}


@dataclass(slots=True, frozen=True)
class ShadowPolicy:
    """Shadow crawl policy applied globally or per-domain."""

    policy_id: str
    enabled: bool = False
    obey_robots: bool = True
    include_patterns: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ()
    js_render: bool = False
    rag: bool = True
    training: bool = True
    ttl_days: int = 7
    rate_limit: RateLimit = RateLimit()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "enabled": self.enabled,
            "obey_robots": self.obey_robots,
            "include_patterns": list(self.include_patterns),
            "exclude_patterns": list(self.exclude_patterns),
            "js_render": self.js_render,
            "rag": self.rag,
            "training": self.training,
            "ttl_days": int(self.ttl_days),
            "rate_limit": self.rate_limit.to_dict(),
        }

    def with_updates(self, payload: Mapping[str, Any]) -> "ShadowPolicy":
        include = payload.get("include_patterns") or payload.get("includePatterns")
        exclude = payload.get("exclude_patterns") or payload.get("excludePatterns")
        include_patterns: tuple[str, ...] = self.include_patterns
        exclude_patterns: tuple[str, ...] = self.exclude_patterns
        if isinstance(include, (list, tuple)):
            include_patterns = tuple(str(item).strip() for item in include if str(item).strip())
        elif isinstance(include, str) and include.strip():
            include_patterns = (include.strip(),)
        if isinstance(exclude, (list, tuple)):
            exclude_patterns = tuple(str(item).strip() for item in exclude if str(item).strip())
        elif isinstance(exclude, str) and exclude.strip():
            exclude_patterns = (exclude.strip(),)

        rate_payload = payload.get("rate_limit") or payload.get("rateLimit") or {}
        if isinstance(rate_payload, Mapping):
            concurrency = _coerce_int(rate_payload.get("concurrency"), self.rate_limit.concurrency)
            delay_ms = _coerce_int(rate_payload.get("delay_ms"), self.rate_limit.delay_ms)
            rate_limit = RateLimit(concurrency=max(1, concurrency), delay_ms=max(0, delay_ms))
        else:
            rate_limit = self.rate_limit

        return replace(
            self,
            enabled=_coerce_bool(payload.get("enabled"), self.enabled),
            obey_robots=_coerce_bool(payload.get("obey_robots") or payload.get("obeyRobots"), self.obey_robots),
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            js_render=_coerce_bool(payload.get("js_render") or payload.get("jsRender"), self.js_render),
            rag=_coerce_bool(payload.get("rag"), self.rag),
            training=_coerce_bool(payload.get("training"), self.training),
            ttl_days=max(1, _coerce_int(payload.get("ttl_days") or payload.get("ttlDays"), self.ttl_days)),
            rate_limit=rate_limit,
        )


class ShadowPolicyStore:
    """Persist global + per-domain shadow crawl policies."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()
        self._global = ShadowPolicy(policy_id="global")
        self._domains: Dict[str, ShadowPolicy] = {}
        self._updated_at = time.time()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            content = json.loads(self._path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(content, Mapping):
            return
        global_payload = content.get("global")
        if isinstance(global_payload, Mapping):
            self._global = self._global.with_updates(global_payload)
        domains_payload = content.get("domains")
        if isinstance(domains_payload, Mapping):
            for key, value in domains_payload.items():
                if not isinstance(value, Mapping):
                    continue
                domain = self._normalize_domain(key)
                if not domain:
                    continue
                self._domains[domain] = ShadowPolicy(policy_id=domain).with_updates(value)
        updated_at = content.get("updated_at")
        try:
            self._updated_at = float(updated_at)
        except (TypeError, ValueError):
            self._updated_at = time.time()

    def _persist(self) -> None:
        payload = {
            "updated_at": self._updated_at,
            "global": self._global.to_dict(),
            "domains": {domain: policy.to_dict() for domain, policy in self._domains.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            # Persistence failures should not crash API callers.
            pass

    def _normalize_domain(self, domain: str | None) -> str:
        if not domain:
            return ""
        normalized = domain.strip().lower()
        return normalized

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "updated_at": self._updated_at,
                "global": self._global.to_dict(),
                "domains": {domain: policy.to_dict() for domain, policy in self._domains.items()},
            }

    def get_global(self) -> ShadowPolicy:
        with self._lock:
            return self._global

    def update_global(self, payload: Mapping[str, Any]) -> ShadowPolicy:
        with self._lock:
            self._global = self._global.with_updates(payload)
            self._updated_at = time.time()
            self._persist()
            return self._global

    def list_domains(self) -> Dict[str, ShadowPolicy]:
        with self._lock:
            return dict(self._domains)

    def get_domain(self, domain: str) -> ShadowPolicy:
        normalized = self._normalize_domain(domain)
        with self._lock:
            if not normalized or normalized not in self._domains:
                return self._global
            return self._domains[normalized]

    def update_domain(self, domain: str, payload: Mapping[str, Any]) -> ShadowPolicy:
        normalized = self._normalize_domain(domain)
        if not normalized:
            raise ValueError("invalid_domain")
        with self._lock:
            existing = self._domains.get(normalized) or ShadowPolicy(policy_id=normalized)
            updated = existing.with_updates(payload)
            self._domains[normalized] = updated
            self._updated_at = time.time()
            self._persist()
            return updated

