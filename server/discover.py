"""Discovery helpers bridging registry seeds and learned web hints."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Sequence
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from rank.authority import AuthorityIndex
from seed_loader.sources import SeedSource
from server.seeds_loader import SeedRegistryEntry, load_seed_registry

LOGGER = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
CURATED_VALUES_PATH = DATA_DIR / "seeds" / "curated_seeds.jsonl"

VALUE_WEIGHT = float(os.getenv("DISCOVER_W_VALUE", "0.5"))
FRESH_WEIGHT = float(os.getenv("DISCOVER_W_FRESH", "0.3"))
AUTH_WEIGHT = float(os.getenv("DISCOVER_W_AUTH", "0.2"))
BASE_WEIGHT = float(os.getenv("DISCOVER_BASE_WEIGHT", "1.0"))

DEFAULT_PER_HOST = int(os.getenv("FRONTIER_PER_HOST", "3"))
DEFAULT_POLITENESS_DELAY = float(os.getenv("FRONTIER_POLITENESS_DELAY", "1.0"))
DEFAULT_RERANK_MARGIN = float(os.getenv("FRONTIER_RERANK_MARGIN", "0.15"))
REGISTRY_BASE_BOOST = float(os.getenv("DISCOVER_REGISTRY_BASE_BOOST", "1.05"))

DEFAULT_LLM_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b-instruct")
DEFAULT_LLM_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "30"))

_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "how",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "where",
    "why",
}


def _keywords(query: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", query.lower())
    filtered = [word for word in words if word not in _STOPWORDS]
    return filtered or words


def _sanitize_url(url: str, base_url: str | None = None) -> Optional[str]:
    candidate = (url or "").strip()
    if not candidate:
        return None
    if candidate.startswith("javascript:"):
        return None
    if candidate.startswith(("http://", "https://")):
        probe = candidate
    elif candidate.startswith("//"):
        probe = "https:" + candidate
    elif base_url:
        probe = urljoin(base_url, candidate)
    else:
        probe = "https://" + candidate.lstrip("/")
    try:
        parsed = urlparse(probe)
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
    path = parsed.path or "/"
    sanitized = f"{scheme}://{parsed.netloc}{path}"
    if parsed.query:
        sanitized = f"{sanitized}?{parsed.query}"
    return sanitized.rstrip("/")


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _heuristic_value(url: str) -> float:
    parsed = urlparse(url)
    path = parsed.path.lower()
    score = 0.6
    for keyword in ("docs", "documentation", "guide", "handbook"):
        if keyword in path:
            score += 0.25
            break
    if any(token in path for token in ("blog", "kb", "support")):
        score += 0.1
    if "api" in path:
        score += 0.1
    if parsed.netloc.lower().endswith((".org", ".io", ".dev")):
        score += 0.1
    return max(0.1, min(score, 1.5))


def _freshness_hint(url: str, source: str) -> float:
    lowered = url.lower()
    if "sitemap" in lowered or source.startswith("sitemap"):
        return 1.0
    if any(token in lowered for token in ("rss", "atom", "feed")):
        return 0.9
    if "blog" in lowered or "news" in lowered:
        return 0.6
    return 0.2 if source == "seed" else 0.1


def score_candidate(*, boost: float, value_prior: float, freshness: float, authority: float) -> float:
    """Apply the weighted scoring model shared with the product brief."""

    return (
        BASE_WEIGHT * boost
        + VALUE_WEIGHT * value_prior
        + FRESH_WEIGHT * freshness
        + AUTH_WEIGHT * authority
    )


def _default_learned_loader() -> Iterable[Mapping[str, object]]:
    try:
        from search import seeds as seed_store  # pylint: disable=import-outside-toplevel
    except ImportError:  # pragma: no cover - circular import guard
        return []
    return seed_store.load_entries()


def _trust_multiplier(value: object) -> float:
    if isinstance(value, (int, float)):
        return max(0.1, float(value))
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 1.0
        lowered = text.lower()
        if lowered == "low":
            return 0.85
        if lowered == "medium":
            return 1.0
        if lowered == "high":
            return 1.2
        try:
            return max(0.1, float(text))
        except ValueError:
            return 1.0
    return 1.0


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _registry_entry_sources(entry: SeedRegistryEntry) -> List[SeedSource]:
    extras = dict(entry.extras)
    tag_payload = extras.pop("tags", None)
    tags = {"registry"}
    if entry.kind:
        tags.add(str(entry.kind))
    if entry.strategy:
        tags.add(str(entry.strategy))
    if isinstance(tag_payload, (list, tuple, set)):
        for tag in tag_payload:
            text = str(tag).strip()
            if text:
                tags.add(text)
    metadata: Dict[str, object] = {
        "registry_id": entry.id,
        "kind": entry.kind,
        "strategy": entry.strategy,
        "trust": entry.trust,
    }
    metadata.update(extras)
    seeds: List[SeedSource] = []
    for url in entry.entrypoints:
        seeds.append(
            SeedSource(
                url=url,
                source=f"registry:{entry.id}",
                tags=set(tags),
                metadata=dict(metadata),
            )
        )
    return seeds


def _load_registry_sources(_: Sequence[str] | None) -> List[SeedSource]:
    seeds: List[SeedSource] = []
    for entry in load_seed_registry():
        seeds.extend(_registry_entry_sources(entry))
    return seeds


def _registry_hit_from_source(source: SeedSource) -> DiscoveryHit | None:
    url = getattr(source, "url", None)
    if not isinstance(url, str):
        return None
    metadata = getattr(source, "metadata", {}) or {}
    multiplier = _trust_multiplier(metadata.get("trust")) if isinstance(metadata, Mapping) else 1.0
    boost = REGISTRY_BASE_BOOST * multiplier
    if isinstance(metadata, Mapping):
        extra_boost = _coerce_float(metadata.get("boost"))
    else:
        extra_boost = None
    if extra_boost is not None and extra_boost > 0:
        boost *= extra_boost
    value_prior = _coerce_float(metadata.get("value_prior")) if isinstance(metadata, Mapping) else None
    freshness = _coerce_float(metadata.get("freshness")) if isinstance(metadata, Mapping) else None
    authority = _coerce_float(metadata.get("authority")) if isinstance(metadata, Mapping) else None
    source_name = getattr(source, "source", None) or "seed"
    return DiscoveryHit(
        url=url,
        source=source_name,
        boost=boost,
        value_prior=value_prior,
        freshness=freshness,
        authority=authority,
    )


@dataclass(slots=True)
class DiscoveryHit:
    """Intermediate hit enriched with semantic signals."""

    url: str
    source: str
    boost: float = 1.0
    value_prior: float | None = None
    freshness: float | None = None
    authority: float | None = None
    score: float | None = None

    def finalize(self, value_map: Mapping[str, float], authority: AuthorityIndex) -> "DiscoveryHit":
        sanitized = _sanitize_url(self.url)
        if not sanitized:
            raise ValueError("invalid url")
        domain = _domain_from_url(sanitized)
        value = self.value_prior if self.value_prior is not None else value_map.get(domain, _heuristic_value(sanitized))
        fresh = self.freshness if self.freshness is not None else _freshness_hint(sanitized, self.source)
        auth = self.authority if self.authority is not None else authority.score_for(domain)
        score = score_candidate(boost=self.boost, value_prior=value, freshness=fresh, authority=auth)
        return DiscoveryHit(
            url=sanitized,
            source=self.source,
            boost=self.boost,
            value_prior=value,
            freshness=fresh,
            authority=auth,
            score=score,
        )


def extract_links(html: str, *, base_url: str | None = None) -> List[str]:
    """Return sanitized hyperlinks discovered in *html*."""

    soup = BeautifulSoup(html or "", "html.parser")
    results: List[str] = []
    for anchor in soup.find_all("a", href=True):
        sanitized = _sanitize_url(anchor.get("href", ""), base_url)
        if sanitized and sanitized not in results:
            results.append(sanitized)
    return results


def wikidata_candidates(entities: Sequence[Mapping[str, object]]) -> Iterator[DiscoveryHit]:
    """Yield hits from Wikidata-style entity payloads."""

    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        urls: List[str] = []
        site_links = entity.get("sitelinks")
        if isinstance(site_links, Mapping):
            for payload in site_links.values():
                if isinstance(payload, Mapping):
                    href = payload.get("url")
                    if isinstance(href, str):
                        urls.append(href)
        claims = entity.get("claims")
        if isinstance(claims, Mapping):
            official = claims.get("P856") or claims.get("official_website")
            if isinstance(official, str):
                urls.append(official)
            elif isinstance(official, Sequence):
                for value in official:
                    if isinstance(value, str):
                        urls.append(value)
        extras = entity.get("urls")
        if isinstance(extras, Sequence):
            for value in extras:
                if isinstance(value, str):
                    urls.append(value)
        for raw in urls:
            sanitized = _sanitize_url(raw)
            if not sanitized:
                continue
            yield DiscoveryHit(url=sanitized, source="wikidata", boost=1.15)


def github_candidates(repos: Sequence[Mapping[str, object]]) -> Iterator[DiscoveryHit]:
    """Yield hits derived from GitHub repository metadata."""

    for repo in repos:
        if not isinstance(repo, Mapping):
            continue
        html_url = repo.get("html_url")
        if isinstance(html_url, str):
            urls = [html_url]
            urls.append(html_url.rstrip("/") + "/wiki")
            urls.append(html_url.rstrip("/") + "/tree/main/docs")
            homepage = repo.get("homepage")
            if isinstance(homepage, str) and homepage:
                urls.append(homepage)
            for url in urls:
                sanitized = _sanitize_url(url)
                if sanitized:
                    yield DiscoveryHit(url=sanitized, source="github", boost=1.2)


def sitemap_candidates(urls: Iterable[str], *, source: str = "sitemap-hint") -> Iterator[DiscoveryHit]:
    """Wrap sitemap URLs as discovery hits."""

    for url in urls:
        sanitized = _sanitize_url(str(url))
        if sanitized:
            yield DiscoveryHit(url=sanitized, source=source, boost=1.1, freshness=1.0)


if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from crawler.frontier import Candidate


class LLMReranker:
    """Thin wrapper around a local Ollama endpoint to rerank borderline URLs."""

    def __init__(
        self,
        endpoint: str | None,
        *,
        model: str | None = None,
        timeout: float | None = None,
        transport: Callable[..., requests.Response] | None = None,
    ) -> None:
        self.endpoint = (endpoint or "").rstrip("/")
        self.model = (model or DEFAULT_LLM_MODEL or "").strip()
        self.timeout = timeout if timeout is not None else DEFAULT_LLM_TIMEOUT
        self._transport = transport or requests.post

    def __call__(self, query: str, candidates: List["Candidate"]) -> List["Candidate"]:
        if not self.endpoint or not self.model or not candidates:
            return candidates
        prompt = self._prompt(query, candidates)
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        try:
            response = self._transport(
                f"{self.endpoint}/api/generate",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.debug("LLM rerank request failed: %s", exc)
            return candidates
        try:
            body = response.json()
            raw = (body or {}).get("response", "").strip()
            order = json.loads(raw)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("LLM rerank response invalid: %s", exc)
            return candidates
        if not isinstance(order, list):
            return candidates
        index: Dict[str, int] = {}
        for position, url in enumerate(order):
            if isinstance(url, str):
                index[url.strip()] = position
        if not index:
            return candidates
        return sorted(candidates, key=lambda c: index.get(c.url, len(index)))

    @staticmethod
    def _prompt(query: str, candidates: Sequence["Candidate"]) -> str:
        bullet = "\n".join(f"- {candidate.url}" for candidate in candidates)
        return (
            "Rank the following documentation URLs for answering the query:\n"
            f"Query: {query}\n"
            f"URLs:\n{bullet}\n"
            "Respond with a JSON array listing the URLs from best to worst."
        )


class DiscoveryEngine:
    """Central orchestrator for focused crawl seed discovery."""

    def __init__(
        self,
        *,
        registry_loader: Callable[[Sequence[str] | None], List[SeedSource]] = _load_registry_sources,
        learned_loader: Callable[[], Iterable[Mapping[str, object]]] = _default_learned_loader,
        authority_factory: Callable[[], AuthorityIndex] = AuthorityIndex.load_default,
        per_host_cap: int | None = None,
        politeness_delay: float | None = None,
        rerank_margin: float | None = None,
    ) -> None:
        self._registry_loader = registry_loader
        self._learned_loader = learned_loader
        self._authority_factory = authority_factory
        self._per_host_cap = DEFAULT_PER_HOST if per_host_cap is None else max(1, int(per_host_cap))
        self._politeness_delay = DEFAULT_POLITENESS_DELAY if politeness_delay is None else max(0.0, float(politeness_delay))
        self._rerank_margin = DEFAULT_RERANK_MARGIN if rerank_margin is None else max(0.0, float(rerank_margin))
        self._authority: AuthorityIndex | None = None
        self._registry_cache: List[SeedSource] | None = None
        self._value_map: Dict[str, float] | None = None
        self._learned_cache: List[Mapping[str, object]] | None = None

    # ------------------------------------------------------------------
    # Cached loaders
    # ------------------------------------------------------------------
    def _authority_index(self) -> AuthorityIndex:
        if self._authority is None:
            self._authority = self._authority_factory()
        return self._authority

    def _registry(self) -> List[SeedSource]:
        if self._registry_cache is None:
            try:
                self._registry_cache = self._registry_loader(None)
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("registry loader failed", exc_info=True)
                self._registry_cache = []
        return list(self._registry_cache)

    def _iter_registry_hits(self) -> Iterator[DiscoveryHit]:
        for source in self._registry():
            hit = _registry_hit_from_source(source)
            if hit is not None:
                yield hit

    def _learned(self) -> List[Mapping[str, object]]:
        if self._learned_cache is None:
            try:
                self._learned_cache = list(self._learned_loader())
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("learned loader failed", exc_info=True)
                self._learned_cache = []
        return list(self._learned_cache)

    def _value_map_cached(self) -> Dict[str, float]:
        if self._value_map is None:
            mapping: Dict[str, float] = {}
            mapping.update(self._load_curated_values())
            for entry in self._learned():
                domain = (entry.get("domain") or "").strip().lower()
                if not domain:
                    continue
                try:
                    score = float(entry.get("score", 0.0))
                except (TypeError, ValueError):
                    score = 0.0
                mapping[domain] = max(mapping.get(domain, 0.0), score)
            self._value_map = mapping
        return dict(self._value_map)

    def _finalize_hits(self, hits: Iterable[DiscoveryHit]) -> List[DiscoveryHit]:
        authority = self._authority_index()
        value_map = self._value_map_cached()
        deduped: Dict[str, DiscoveryHit] = {}
        for hit in hits:
            try:
                finalized = hit.finalize(value_map, authority)
            except ValueError:
                continue
            existing = deduped.get(finalized.url)
            if existing is None or (finalized.score or 0.0) > (existing.score or 0.0):
                deduped[finalized.url] = finalized
        return list(deduped.values())

    def _build_frontier(
        self,
        query: str,
        limit: int,
        discovery_hints: Sequence[DiscoveryHit],
        rerank_fn: Optional[Callable[[str, List["Candidate"]], List["Candidate"]]],
    ) -> List["Candidate"]:
        from crawler.frontier import build_frontier  # local import to avoid cycles

        return build_frontier(
            query,
            budget=limit,
            discovery_hints=discovery_hints,
            per_host_cap=self._per_host_cap,
            politeness_delay=self._politeness_delay,
            rerank_fn=rerank_fn,
            rerank_margin=self._rerank_margin,
        )

    def _resolve_rerank_fn(
        self,
        use_llm: bool,
        model: Optional[str],
        rerank_fn: Optional[Callable[[str, List["Candidate"]], List["Candidate"]]],
    ) -> Optional[Callable[[str, List["Candidate"]], List["Candidate"]]]:
        if rerank_fn is not None:
            return rerank_fn
        if use_llm:
            return LLMReranker(
                os.getenv("OLLAMA_URL", os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")),
                model=model,
            )
        return None

    def registry_frontier(
        self,
        query: str,
        *,
        limit: int,
        use_llm: bool = False,
        model: Optional[str] = None,
        rerank_fn: Optional[Callable[[str, List["Candidate"]], List["Candidate"]]] = None,
    ) -> List["Candidate"]:
        hits = list(self._iter_registry_hits())
        finalized = self._finalize_hits(hits)
        if not finalized:
            return []
        reranker = self._resolve_rerank_fn(use_llm, model, rerank_fn)
        return self._build_frontier(query, limit, finalized, reranker)

    @staticmethod
    def _load_curated_values() -> Dict[str, float]:
        values: Dict[str, float] = {}
        if not CURATED_VALUES_PATH.exists():
            return values
        try:
            with CURATED_VALUES_PATH.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        continue
                    url = payload.get("url")
                    if not isinstance(url, str):
                        continue
                    domain = _domain_from_url(url)
                    try:
                        score = float(payload.get("value_prior", 0.0))
                    except (TypeError, ValueError):
                        score = 0.0
                    values[domain] = max(values.get(domain, 0.0), score)
        except OSError:  # pragma: no cover - filesystem issues
            return values
        return values

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def discover(
        self,
        query: str,
        *,
        limit: int,
        extra_seeds: Optional[Sequence[str]] = None,
        html_snippets: Optional[Sequence[str]] = None,
        wikidata_entities: Optional[Sequence[Mapping[str, object]]] = None,
        github_repos: Optional[Sequence[Mapping[str, object]]] = None,
        sitemap_urls: Optional[Sequence[Iterable[str]]] = None,
        use_llm: bool = False,
        model: Optional[str] = None,
        rerank_fn: Optional[Callable[[str, List["Candidate"]], List["Candidate"]]] = None,
    ) -> List["Candidate"]:
        """Return ranked crawl seeds for *query*."""

        q = (query or "").strip()
        if not q:
            return []
        limit = max(1, int(limit))
        keywords = set(_keywords(q))

        hits: List[DiscoveryHit] = []
        registry_fallback: List[DiscoveryHit] = []

        for hit in self._iter_registry_hits():
            registry_fallback.append(hit)
            if keywords and not any(token in hit.url.lower() for token in keywords):
                continue
            hits.append(hit)

        for entry in self._learned():
            domain = (entry.get("domain") or "").strip()
            if not domain:
                continue
            url = entry.get("url")
            if isinstance(url, str) and url.strip():
                target = url
            else:
                target = f"https://{domain}"
            try:
                score = float(entry.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            hits.append(DiscoveryHit(url=target, source="learned", boost=1.1, value_prior=score))

        for snippet in html_snippets or []:
            for url in extract_links(snippet):
                hits.append(DiscoveryHit(url=url, source="html", boost=1.2))

        for url in extra_seeds or []:
            sanitized = _sanitize_url(url)
            if sanitized:
                hits.append(DiscoveryHit(url=sanitized, source="manual", boost=1.25))

        if wikidata_entities:
            hits.extend(list(wikidata_candidates(wikidata_entities)))

        if github_repos:
            hits.extend(list(github_candidates(github_repos)))

        if sitemap_urls:
            for group in sitemap_urls:
                hits.extend(list(sitemap_candidates(group)))

        if not hits and registry_fallback:
            hits.extend(registry_fallback)

        discovery_hints = self._finalize_hits(hits)
        if not discovery_hints:
            return []

        reranker = self._resolve_rerank_fn(use_llm, model, rerank_fn)
        return self._build_frontier(q, limit, discovery_hints, reranker)


__all__ = [
    "DiscoveryEngine",
    "DiscoveryHit",
    "LLMReranker",
    "extract_links",
    "github_candidates",
    "sitemap_candidates",
    "score_candidate",
    "wikidata_candidates",
]
