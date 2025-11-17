# Backend Contracts v1

This document is the source of truth for every externally callable backend API that powers the Self-Hosted Search Engine.  Client SDKs, agents, and manual operators must treat these shapes as frozen unless we explicitly version a breaking change.

## Versioning and change policy

- **Current version:** `v1` (alpha frozen).  Any breaking change (field removal/rename, new required inputs, status shifts) must go through a conscious upgrade path.
- **Update steps:** when an endpoint’s shape changes, update this document, add/adjust regression tests under `tests/`, and call out the migration in the changelog or docs release notes.
- **Compatibility:** optional fields may be added as long as they default safely and are documented here.

## Conventions

| Topic | Contract |
| --- | --- |
| Base URL | Every endpoint is rooted under `https://<host>/api`.  Browser-related endpoints add `/browser`, repo tooling adds `/repo`, etc. |
| Media types | Request/response bodies are JSON.  Streaming chat also uses NDJSON over SSE. |
| Error envelope | Errors return `{ "ok": false, "error": { "code": string, "message": string, "details"?: {...} } }` with HTTP 4xx/5xx.  Legacy endpoints that still emit `{ "error": "..." }` should be migrated before Backend v2. |
| Success envelope | Core endpoints return `{ "ok": true, "data": {...} }` and keep legacy top-level keys such as `items`, `thread`, or `job` for backwards compatibility. |
| Pagination | Query params `limit` (default 50) and `offset` appear on list endpoints.  They must clamp to sane bounds and never throw on negative input. |
| IDs | Threads, jobs, bundles, etc. accept caller-provided IDs but will generate stable UUIDv4 strings when omitted. |

---

## Extension Points v1

- **Jobs / long-running operations**
  - Introduce new work by registering a `jobs.type` (e.g., `bundle_export`).
  - Mirror lifecycle updates through `AppStateDB.create_job` / `update_job`,
    keep `jobs` table fields consistent, and document the type in this file.
- **Bundle components**
  - Add the component name to `manifest.components` and implement both
    `bundle_io.export_bundle` and `bundle_io.import_bundle` paths with
    idempotent dedupe logic.
  - Ship regression tests covering export/import round-trips.
- **Repo tools**
  - Mount new helpers under `/api/repo/...`, enforce change budgets and
    repo-root sandboxing, and log state changes via `repo_changes`.
  - Any command execution must go through the allow-listed configuration and
    record a `repo_*` job when applicable.
- **HydraFlow entities**
  - Prefer enriching existing tables (new metadata fields, enums, or payloads)
    before introducing new tables.  This keeps bundles, privacy deletes, and
    cross-component joins simple.

---

## Chat + reasoning

| Endpoint | Method | Request | Response |
| --- | --- | --- | --- |
| `/api/chat` | `POST` | `ChatRequest` payload validated by `backend/app/api/schemas.py`.  Required: `messages` (≥1).  Optional: `model`, `stream` (bool), `tools`, `context`, `chat_id`, `tab_id`, etc. | JSON `ChatResponsePayload` with `{ reasoning, answer, message, citations[], model?, trace_id?, autopilot? }`.  Response headers always include `X-Request-Id`. |
| `/api/chat/stream` | `POST` | Same payload, but forces streaming semantics. | Server-Sent Events (SSE) using NDJSON frames: `metadata`, repeated `delta` events, and terminal `complete` or `error`.  The terminal `complete` payload wraps the same `ChatResponsePayload` as `/api/chat`. |
| `/api/chat/schema` | `GET` | None. | Echoes the normalized schema (`ChatRequest`, `ChatResponsePayload`, stream event contracts) for tool generators. |

**Caller expectations**

- Provide at least one `user` message; empty payloads return HTTP 400 `{"error": "EMPTY_MESSAGE"}`.
- SSE responses are single-flight per `chat_id`.  Clients should honor `X-Request-Id` for tracing and deduplicate if they retry.

---

## HydraFlow threads & messages

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/threads` | `GET` | Returns `{ items: Thread[] }`.  Each thread includes `id`, `title`, `description`, `origin`, timestamps, and optional metadata. |
| `/api/threads` | `POST` | Accepts `{ id?, title?, description?, origin?, metadata? }`.  Missing `id` creates a thread.  Returns `{ id, thread }` (201). |
| `/api/threads/<thread_id>` | `GET` | Returns `{ thread }` or `404 {"error": "not_found"}`. |
| `/api/threads/<thread_id>` | `DELETE` | Cascades deletion into messages, tasks, memories, and detaches linked tabs.  Response `{ deleted: thread_id, stats: { threads, messages, tasks, memories, tabs } }`. |
| `/api/threads/<thread_id>/messages` | `GET` | Query param `limit` (default 50) returns chronological `{ items: Message[] }`. |
| `/api/threads/<thread_id>/messages` | `POST` | Body `{ role, content, parent_id?, id?, metadata?, tokens? }`.  Roles limited to `user/assistant/system/tool`.  Response `{ id }` (201). |

Message records include `id`, `thread_id`, `role`, `content`, `tokens`, `metadata`, and timestamps so embeddings, tool invocations, and audits can rehydrate the conversation precisely.

---

## HydraFlow tasks & events

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/tasks` | `GET` | Filters: `status`, `thread_id`, `limit`. Returns `{ items: Task[] }`. |
| `/api/tasks` | `POST` | Body `{ title, description?, thread_id?, status?, priority?, due_at?, owner?, metadata?, result? }`.  Response `{ id, task }` (201). |
| `/api/tasks/<task_id>` | `GET`/`PATCH` | Fetch or update status/metadata/result.  PATCH accepts any subset of mutable fields. |
| `/api/tasks/<task_id>/events` | `GET`/`POST` | Events capture lifecycle traces (`type`, `detail`, `metadata`). |

Tasks and events share the same `{id, thread_id, status, priority, due_at, owner, metadata, result}` contract, keeping frontends and agents aligned with the planner UI.

---

## Memory & embeddings

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/memory` | `GET` | Query by `thread_id`, `limit`, or `q` (full-text search).  Returns `{ items: Memory[] }`. |
| `/api/memory` | `POST` | Upserts `{ id?, thread_id, title?, content, tags?, metadata?, importance? }`. |
| `/api/memory/<memory_id>` | `DELETE` | Response `{ deleted: memory_id }` when present, `404` otherwise. |
| `/api/embeddings/build` | `POST` | Accepts `{ thread_id?, memory_ids?, force?: bool }` to recompute memory embeddings and returns `{ job_id }` for async tracking. |

Memories mirror the schema persisted in `memory_embeddings`/`memories` tables so exported bundles stay consistent.

---

## Browser ↔ thread linkage & history

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/browser/tabs` (`GET`) | Lists current tabs `{ items: Tab[] }`. |
| `/api/browser/tabs/<tab_id>` (`GET`) | Returns `{ tab }` or `404`.  `tab_id` is opaque (Electron BrowserView ID). |
| `/api/browser/tabs/<tab_id>/thread` (`POST`) | Body `{ thread_id?, title?, description?, origin? }`.  Returns `{ tab, thread, thread_id }` and automatically calls `ensure_llm_thread`. |
| `/api/browser/history` (`GET`) | Filters: `limit`, `query`, `from`, `to`.  Returns `{ items: HistoryEntry[] }`. |
| `/api/browser/history` (`POST`) | Body `{ tab_id?, url (required), title?, referrer?, status_code?, content_type? }`.  Publishes an agent-trace event when validation fails. |
| `/api/browser/history/<history_id>` (`DELETE`) | Removes a single row; response `{ deleted: history_id }`. |
| `/api/browser/history` (`DELETE`) | Bulk purge.  Query/body filters: `domain`, `older_than_days`, `tab_id`.  Response includes `{ deleted, mode }`. |
| `/api/visits` (`GET`/`POST`) | Mirrors `history` for fine-grained visit telemetry, enforcing `{ tab_id, url, started_at }`. |

When history rows drive search or bundles, the backend automatically clears tab bindings that reference deleted rows, preserving UI invariants described in `docs/backend_architecture.md`.

---

## Overview, metrics, and diagnostics

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/overview` | `GET` | Aggregates counts for history rows, normalized docs, tasks, memories, job stats, and storage footprint (cached for 5 minutes). |
| `/api/metrics` | `GET` | Emits Prometheus-friendly text with process/runtime gauges. |
| `/api/system/check` | `GET` | Fast status probe used by the desktop shell; returns `{ ok: true, components: {...} }`. |
| `/api/diagnostics/run` | `POST` | Body `{ smoke?: bool }`.  Kicks off a diagnostics job and returns `{ job_id }`. |
| `/api/index/snapshot` / `/api/index/site` | `POST` | Accept `{ url, scope }` payloads, enforce allow-listed hosts, and return `{ job_id }`. |
| `/api/embeddings/health` + `/api/llm/health` | `GET` | Lightweight probes surfaced in the UI.

---

## Jobs ledger & bundles

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/jobs` | `GET` | Filters by `status` and `type`.  Returns `{ items: Job[] }` sorted newest-first. |
| `/api/jobs/<job_id>` | `GET` | Returns `{ job }` or `404`. |
| `/api/jobs/<job_id>/status` | `GET` | Returns merged runner + DB status, including `{ phase, progress, eta_seconds, steps_total, steps_completed, stats }`. |
| `/api/jobs/<job_id>/log` | `GET` | Streams the job log (download by default). |
| `/api/jobs` | `DELETE` | Body/query accepts `statuses[]` and `older_than_days` (default 30).  Response `{ deleted, statuses, older_than_days }`. |
| `/api/export/bundle` | `GET` | Query `component=threads&component=browser_history` etc.  Returns `{ job_id, bundle_path, manifest }` after synchronous export and records a `bundle_export` job. |
| `/api/import/bundle` | `POST` | Body `{ bundle_path, components?[] }`.  Validates file, performs import, and responds `{ job_id, imported: { threads, messages, tasks, history } }`. |

Jobs are append-only records kept in SQLite; pruning is safe once jobs have succeeded or exceeded retention.

---

## Repository tooling

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/repo/list` | `GET` | Lists repos registered in `AppStateDB` along with `root`, `description`, `allowed_checks`, and budgets. |
| `/api/repo/<id>/status` | `GET` | Returns `{ repo, git_status }` where `git_status` includes `branch`, `dirty`, `ahead`, `behind`, and a short `changes[]` list. |
| `/api/repo/<id>/propose_patch` | `POST` | Body `{ files: [{ path, diff?, additions?, deletions?, delete? }], message?, request_id? }`.  Enforces max files/LOC (`MAX_FILES`, `MAX_LOC`), validates paths remain inside the repo root, and writes nothing to disk.  Response `{ ok: true, files, totals: { files, loc }, message? }`. |
| `/api/repo/<id>/apply_patch` | `POST` | Same payload, but writes via atomic temp files.  Response `{ job_id, applied: [{ path, action }], totals, repo_change_id }`.  Also records a `repo_apply_patch` job/change entry. |
| `/api/repo/<id>/run_checks` | `POST` | Body `{ command?: string[] }`.  The command must match the server-registered allow-list.  Response `{ job_id, command, status }` and logs to both `jobs` and `repo_changes`. |

All repo endpoints reject absolute paths, `..` traversal, and budgets overrun with `{ "error": "budget_exceeded" }` plus details so clients can adjust diffs deterministically.

---

## Search, discovery, and research

| Endpoint | Method | Notes |
| --- | --- | --- |
| `/api/search` | `POST` | Body `{ query, limit?, filters? }`.  Returns `{ results: [{ url, title, snippet, score, source }] }` blending BM25 + vector hits. |
| `/api/reasoning` | `POST` | Accepts `{ query, mode?, thread_id? }`.  Triggers chain-of-thought retrieval plus optional planner/autopilot directives. |
| `/api/discovery/candidates` | `GET`/`POST` | Surfaces crawl targets derived from HydraFlow memories, history, and seeds when local recall is low. |
| `/api/web/search` | `POST` | Proxy to privacy-aware third-party search providers, returning normalized `{ results }` objects. |

These endpoints inherit the same `{ error }` envelope and share job IDs when they schedule background work (e.g., `focused_crawl`).

---

## Maintenance-mode agent prompt

Use the following system prompt (or equivalent) when automating repository work so we default to safe, non-breaking maintenance until Backend Contracts v1 genuinely need an upgrade:

```
You are maintaining and extending a local-first browser + search engine backend.

The system already implements HydraFlow-style memory/tasks, browser↔thread linkage, repo tools, bundles, jobs, privacy endpoints, and docs. The architecture and Backend Contracts v1 are considered **alpha-frozen**.

Your priorities in each run:

1. KEEP implementation aligned with Backend Contracts v1
   - Always read docs/backend_contracts.md and docs/backend_architecture.md.
   - If code violates the contracts in small ways (response envelope, missing fields), prefer fixing the code and adding tests.
   - If the existing behavior is clearly better than the contract, update both the contract doc and the tests to reflect the new truth.

2. DEFAULT to non-breaking work
   - Add or improve tests.
   - Fix bugs and edge cases.
   - Improve performance, safety, and observability.
   - Add new capabilities by:
     - Adding new job types.
     - Adding new bundle components.
     - Adding metadata or filters to existing entities/endpoints.
   - Avoid:
     - Changing existing endpoint shapes.
     - Renaming or removing fields.
     - Adding new top-level APIs, unless explicitly requested.

3. When breaking changes are truly necessary:
   - Update:
     - Implementation
     - Tests
     - docs/backend_contracts.md
     - docs/backend_architecture.md (if needed)
   - Leave clear migration notes in docs/backend_contracts.md.

4. Never silently drift from the contracts
   - If you touch an endpoint described in backend_contracts.md:
     - Re-read the contract.
     - Ensure tests cover the intended shape.
     - Keep `{ ok, data }` / `{ ok: false, error: { ... } }` envelopes consistent.

If you are not explicitly asked to add a new feature, focus on:
- Robustness (transactionality, sandboxing, error handling).
- Performance (caching, pruning, avoiding N+1 queries).
- Developer ergonomics (small refactors, clearer code paths, better logging).
Ensure tests stay green at the end of each run.
```

Document history:
- **2025-02-22:** Initial snapshot of Backend Contracts v1 + maintenance-mode agent prompt.
