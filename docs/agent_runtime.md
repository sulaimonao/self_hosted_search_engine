# Agent runtime discovery fallbacks

The agent runtime builds crawl candidates from multiple sources whenever a query
returns too few local results. The fallback flow prioritizes previously seen
content and curated entrypoints to keep discovery relevant and policy compliant:

1. **Search hits** – Any URLs returned from the vector/BM25 search path are
   sanitized and deduplicated before being queued.
2. **Recent discoveries** – If no hits are available, the runtime scans the
   document store for the most recently saved pages and reuses those canonical
   URLs. This allows fresh crawl results to bootstrap subsequent turns.
3. **Seed registry suggestions** – Curated registry entrypoints
   (`seeds/registry.yaml`) are loaded and scored using tag, strategy, and trust
   metadata. High-trust feeds and Wikipedia portals surface first, ensuring that
   crawl work always starts from vetted domains.
4. **Domain heuristics** – Finally, deterministic heuristics derive topical
   targets such as Wikipedia articles and evergreen research hubs using the
   original query text.

Every candidate is normalized to an allowed HTTP(S) URL before enqueueing the
frontier. This keeps the crawl queue free of unsupported schemes or duplicate
entries while still guaranteeing that each fallback list contains actionable,
real-world targets for cold-start scenarios.
