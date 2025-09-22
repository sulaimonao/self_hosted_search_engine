"""Cold-start orchestration for building the knowledge base."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Sequence

from crawler.frontier import Candidate

from ..data.store import VectorStore
from .chunk import TokenChunker
from .crawl import CrawlClient, CrawlError
from .embed import OllamaEmbedder

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from server.discover import DiscoveryEngine
    from server.learned_web_db import LearnedWebDB

CandidateProvider = Callable[[str, int, bool, str | None], Sequence[Candidate]]
LLMSeedProvider = Callable[[str, int, str | None], Sequence[str]]

LOGGER = logging.getLogger(__name__)


class ColdStartIndexer:
    """Coordinates crawl, chunk, embed, store pipeline when data is missing."""

    def __init__(
        self,
        store: VectorStore,
        crawler: CrawlClient,
        chunker: TokenChunker,
        embedder: OllamaEmbedder,
        discovery_engine: DiscoveryEngine | None = None,
        learned_db: LearnedWebDB | None = None,
        candidate_provider: CandidateProvider | None = None,
        llm_seed_provider: LLMSeedProvider | None = None,
        max_pages: int = 5,
    ) -> None:
        self._store = store
        self._crawler = crawler
        self._chunker = chunker
        self._embedder = embedder
        self._discovery_engine = discovery_engine
        self._learned_db = learned_db
        self._candidate_provider = candidate_provider
        self._llm_seed_provider = llm_seed_provider
        self._max_pages = max_pages

    def build_index(
        self, query: str, *, use_llm: bool = False, llm_model: str | None = None
    ) -> int:
        candidates = list(
            (self._candidate_provider or self._discover_candidates)(
                query, self._max_pages, use_llm, llm_model
            )
            or []
        )
        if not candidates:
            return 0

        indexed = 0
        seen: set[str] = set()
        for candidate in candidates:
            if indexed >= self._max_pages:
                break
            url = getattr(candidate, "url", "")
            if not isinstance(url, str) or not url:
                continue
            if url in seen:
                continue
            seen.add(url)
            self._persist_discovery(query, candidate)
            try:
                result = self._crawler.fetch(url)
            except CrawlError:
                continue
            if result is None:
                continue
            if not self._store.needs_update(url, result.etag, result.content_hash):
                continue
            chunks = self._chunker.chunk_text(result.text)
            if not chunks:
                continue
            embeddings = self._embedder.embed_documents([chunk.text for chunk in chunks])
            if not embeddings:
                continue
            self._store.upsert(
                url=url,
                title=result.title,
                etag=result.etag,
                content_hash=result.content_hash,
                chunks=chunks,
                embeddings=embeddings,
            )
            indexed += 1
        return indexed

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------
    def _ensure_discovery_engine(self) -> DiscoveryEngine:
        if self._discovery_engine is None:
            from server.discover import DiscoveryEngine as _DiscoveryEngine  # local import

            self._discovery_engine = _DiscoveryEngine()
        return self._discovery_engine

    def _ensure_learned_db(self) -> LearnedWebDB | None:
        if self._learned_db is None:
            try:
                from server.learned_web_db import get_db as _get_db  # local import

                self._learned_db = _get_db()
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("failed to initialize learned web db", exc_info=True)
                self._learned_db = None
        return self._learned_db

    def _discover_candidates(
        self, query: str, limit: int, use_llm: bool, llm_model: str | None
    ) -> Sequence[Candidate]:
        llm_urls: list[str] = []
        if use_llm and self._llm_seed_provider is not None:
            for raw in self._llm_seed_provider(query, limit, llm_model):
                if isinstance(raw, str):
                    candidate = raw.strip()
                    if candidate and candidate not in llm_urls:
                        llm_urls.append(candidate)

        engine = self._ensure_discovery_engine()
        frontier = list(
            engine.discover(
                query,
                limit=max(1, int(limit)),
                extra_seeds=llm_urls,
                use_llm=use_llm,
                model=llm_model,
            )
        )
        if frontier:
            return frontier
        return engine.registry_frontier(
            query,
            limit=max(1, int(limit)),
            use_llm=use_llm,
            model=llm_model,
        )

    def _persist_discovery(self, query: str, candidate: Candidate) -> None:
        db = self._ensure_learned_db()
        if db is None:
            return
        url = getattr(candidate, "url", "")
        if not isinstance(url, str) or not url:
            return
        score_value = getattr(candidate, "score", None)
        if score_value is None:
            score_value = getattr(candidate, "weight", 0.0)
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            score = 0.0
        source = getattr(candidate, "source", None)
        reason = f"coldstart:{source or 'seed'}"
        try:
            db.record_discovery(
                query,
                url,
                reason=reason,
                score=score,
                source=source,
            )
        except Exception:  # pragma: no cover - defensive logging only
            LOGGER.debug("failed to record discovery for url=%s", url, exc_info=True)


__all__ = ["ColdStartIndexer"]
