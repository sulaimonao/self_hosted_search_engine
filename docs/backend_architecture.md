# Backend Architecture Overview

This document captures how the major backend services introduced across the multi-phase plan fit together.

## User profile model (Backend v1)
- One repository + data directory hosts exactly **one** user profile.  All
  persisted state (HydraFlow threads/messages/tasks, browser tabs/history,
  bundles, jobs, repo tooling, etc.) is scoped to that profile.
- Multi-user / multi-tenant operation inside a single database is intentionally
  out of scope for Backend v1.  Supporting multiple people means running
  multiple independent data directories (one per user) instead of sprinkling
  `user_id` columns across every table.
- Frontends or agents that need to impersonate different users should switch
  between data directories explicitly so each profile keeps isolated storage,
  privacy controls, and bundle exports.

## HydraFlow memory/tasks
- Tables: `llm_threads`, `llm_messages`, `tasks`, `task_events`, `memory_embeddings`.
- APIs: `/api/chat`, `/api/hydraflow`, `/api/memory`, `/api/tasks`, `DELETE /api/threads/<id>`.
- Data flow: `/api/chat` writes user + assistant messages into `llm_messages`, updates thread metadata, and links relevant tasks/memories. Embeddings + events feed downstream ranking/indexing services. Privacy clean-up now flows through `DELETE /api/threads/<id>`, which deletes the thread, cascades messages, removes linked tasks/memories, and detaches bound tabs before recording the audit stats in the response.

## Browser, tabs, and history linkage
- Tables: `tabs`, `history`, `bookmarks`.
- APIs: `/api/browser/*`, `/api/chat` (tab binding), `/api/visits`.
- Flow: Browser telemetry lands in `history`; tabs maintain the currently focused history row + linked thread_id. Bundles now export/import history to preserve that context. Privacy endpoints (`DELETE /api/browser/history/<id>` and `DELETE /api/browser/history`) remove individual rows or filtered batches (domain/time/clear-all) while clearing tab pointers so the UI never references deleted history.

## Overview/dashboard
- API: `/api/overview` aggregates counts for browser history, normalized docs, tasks, memories, storage consumption, and background job stats.
- Used by the desktop shell to provide a quick health snapshot before orchestrating new work.
- Storage size calculations are cached in-process (300s TTL keyed by resolved paths) so repeated `/api/overview` calls do not walk large directory trees more than necessary. A TODO remains to add a stress/micro-bench harness once the repo grows a standard pattern.

## Repository tooling (Phase 4)
- Tables: `repos`, `repo_changes` plus the shared `jobs` ledger.
- APIs: `/api/repo/list`, `/status`, `/propose_patch`, `/apply_patch`, `/run_checks`.
- Flow: repos are registered with allowed operations + optional check commands. `propose_patch` enforces change budgets; `apply_patch` rewrites files directly from structured payloads using temp-file swaps for durability, logs to `repo_changes`, and emits `repo_apply_patch` jobs. `run_checks` executes only the pre-configured command (overrides must match exactly), captures stdout/stderr, records a `repo_run_checks` job, and logs a repo change for auditing. Patch paths are validated against the repo root so no payload can escape via `../` traversal.

## Bundles and import/export (Phase 5)
- Components covered: `threads`, `messages`, `tasks`, and now `browser_history`.
- APIs: `/api/export/bundle`, `/api/import/bundle` (both tracked as jobs).
- Deduping: imports upsert threads/messages by id+timestamp, tasks by id, and history entries by `(url, visited_at)`.
- Bundles include a manifest enumerating included components so incremental restoration is possible.

- Table: `jobs` (+ `job_status`).
- APIs: `/api/jobs`, `/api/jobs/<id>`, `/api/jobs/<id>/status`, `DELETE /api/jobs`.
- Sources: bundle import/export, repo apply/checks, manual refresh (`focused_crawl`) via the refresh worker, and future indexing/embedding tasks.
- Flow: Long-running operations create a job row (`status=queued`), transition to `running` with `started_at`, and resolve to `succeeded`/`failed` with structured `result` payloads and optional `error` text. `/api/jobs` supports filtering by `status` and `type` to let operators focus on relevant work. Operators can now prune old succeeded jobs via `DELETE /api/jobs` (defaults to removing succeeded jobs older than 30 days) to keep the ledger compact; helper `AppStateDB.prune_jobs` is available for scheduled maintenance tasks.

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

## Request lifecycle examples

### Chat with tab binding + memory
1. Desktop shell binds/ensures a tab via `POST /api/browser/tabs/<tab_id>/thread`, receiving a thread_id.
2. `/api/chat` requests include that `tab_id`, so the assistant persists messages under the shared `llm_threads` row and updates tab metadata.
3. When memory extraction runs, `/api/memory` (or background jobs) upserts summaries tied to the thread, so subsequent `/api/chat` calls retrieve structured memories without re-fetching history.
4. If the user clears the conversation, `DELETE /api/threads/<thread_id>` removes the thread, messages, associated tasks/memories, and detaches any tabs.

### Repo edit (propose → apply → run checks)
1. The agent submits candidate edits to `/api/repo/<id>/propose_patch`; budget validation (max files/LOC + repo-root enforcement) runs before anything touches disk.
2. `/api/repo/<id>/apply_patch` writes each file via temp files + atomic renames, records a `repo_apply_patch` job, and logs a row in `repo_changes` with detailed stats.
3. `/api/repo/<id>/run_checks` executes the configured allow-listed command (payload overrides must match exactly), captures stdout/stderr, and records another job/change entry. Operators can inspect the results via `/api/jobs/<job_id>`.

### Bundle export/import with job monitoring
1. Clients call `/api/export/bundle` with the desired components; the handler schedules a `bundle_export` job and immediately returns the job_id.
2. Progress is streamed through `jobs` + optional `job_status` rows, so `/api/jobs/<job_id>/status` reflects up-to-date phase/progress.
3. Imports (`/api/import/bundle`) follow the same pattern and merge threads/messages/tasks/history idempotently. After long-running import/export waves, operators can prune the associated jobs via `DELETE /api/jobs` to keep the ledger lean.

## Developer notes
- Long-running/background jobs should register new job types in `AppStateDB.create_job` and surface progress through `AppStateDB.upsert_job_status`; pruning is handled by `AppStateDB.prune_jobs` + `DELETE /api/jobs`.
- New bundle components should be added to `backend/app/api/bundle.py` plus the import/export helpers in `AppStateDB` (ensure dedupe logic exists before wiring the API).
- Repository tools live in `backend/app/api/repo.py`; always validate patch paths, respect change budgets, and log via `state_db.record_repo_change`. Commands executed via `/run_checks` must be explicitly configured server-side.
- Browser/history privacy: add any additional delete/clear behaviors inside `AppStateDB.purge_history` so tab/bookmark relationships stay consistent.
- Performance TODO: add a reusable micro-bench harness for `/api/overview` + repo tooling once the repo establishes a stress-test pattern; for now the storage cache and tests guard against regressions.
