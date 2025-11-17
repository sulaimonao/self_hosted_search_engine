# Backend Architecture Overview

This document captures how the major backend services introduced across the multi-phase plan fit together.

## HydraFlow memory/tasks
- Tables: `llm_threads`, `llm_messages`, `tasks`, `task_events`, `memory_embeddings`.
- APIs: `/api/chat`, `/api/hydraflow`, `/api/memory`, `/api/tasks`.
- Data flow: `/api/chat` writes user + assistant messages into `llm_messages`, updates thread metadata, and links relevant tasks/memories. Embeddings + events feed downstream ranking/indexing services.

## Browser, tabs, and history linkage
- Tables: `tabs`, `history`, `bookmarks`.
- APIs: `/api/browser/*`, `/api/chat` (tab binding), `/api/visits`.
- Flow: Browser telemetry lands in `history`; tabs maintain the currently focused history row + linked thread_id. Bundles now export/import history to preserve that context.

## Overview/dashboard
- API: `/api/overview` aggregates counts for browser history, normalized docs, tasks, memories, storage consumption, and background job stats.
- Used by the desktop shell to provide a quick health snapshot before orchestrating new work.

## Repository tooling (Phase 4)
- Tables: `repos`, `repo_changes` plus the shared `jobs` ledger.
- APIs: `/api/repo/list`, `/status`, `/propose_patch`, `/apply_patch`, `/run_checks`.
- Flow: repos are registered with allowed operations + optional check commands. `propose_patch` enforces change budgets; `apply_patch` rewrites files directly from structured payloads, logs to `repo_changes`, and emits `repo_apply_patch` jobs. `run_checks` executes the configured command (default or per-request), captures stdout/stderr, records a `repo_run_checks` job, and logs a repo change for auditing.

## Bundles and import/export (Phase 5)
- Components covered: `threads`, `messages`, `tasks`, and now `browser_history`.
- APIs: `/api/export/bundle`, `/api/import/bundle` (both tracked as jobs).
- Deduping: imports upsert threads/messages by id+timestamp, tasks by id, and history entries by `(url, visited_at)`.
- Bundles include a manifest enumerating included components so incremental restoration is possible.

## Jobs system (Phase 6)
- Table: `jobs` (+ `job_status`).
- APIs: `/api/jobs`, `/api/jobs/<id>`, `/api/jobs/<id>/status`.
- Sources: bundle import/export, repo apply/checks, manual refresh (`focused_crawl`) via the refresh worker, and future indexing/embedding tasks.
- Flow: Long-running operations create a job row (`status=queued`), transition to `running` with `started_at`, and resolve to `succeeded`/`failed` with structured `result` payloads and optional `error` text. `/api/jobs` supports filtering by `status` and `type` to let operators focus on relevant work.

## Data-flow snapshot
```
Browser -> history/tabs --+--> Bundles (export/import)
                          |
                          +--> Overview metrics
Repo tools -> repo_changes -> jobs ledger -> /api/jobs
HydraFlow threads/messages/tasks -> Bundles + Overview
Refresh worker -> crawl jobs -> jobs ledger -> Overview
```

This document will evolve as we wire more phases (indexes, embeddings, storage clean-up) into the same primitives.
