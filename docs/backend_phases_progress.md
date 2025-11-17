# Backend Phases Progress

| Phase | Status       | Notes |
|-------|--------------|-------|
| 0     | Complete     | `docs/backend_phase0_summary.md` documents current stack. |
| 1     | Complete     | Added HydraFlow schema, migrations, APIs, and chat wiring. |
| 2     | In progress  | Tabs now store linked thread IDs/history snapshots, `/api/browser/tabs` exposes bindings, and chat reuses/binds tab threads. Need richer page snapshot context. |
| 3     | In progress  | `/api/overview` aggregates browser/doc/task/memory counts plus storage sizes; future work: job/index health details. |
| 4     | Complete     | Safe repo tooling now includes `/apply_patch` (structured writes with change budgets + repo change ledger) and `/run_checks` (configurable commands + job tracking). |
| 5     | In progress  | Bundles now round-trip browser history (with `(url, visited_at)` dedupe) in addition to threads/messages/tasks; next up: documents/pages + richer imports. |
| 6     | In progress  | Jobs ledger tracks bundle ops, repo apply/checks, and focused crawl refresh jobs; filtering added to `/api/jobs`. Still need embedding/index operations. |
| 7     | Started      | Added `docs/backend_architecture.md` and cleanup hooks while filling in repo/bundle/job documentation. |

## Run Notes
- Initialized tracker.
- Phase 1: added llm_threads/messages/tasks/events/memory migrations, APIs, and chat persistence.
- Phase 2: linked tabs to threads/history metadata, exposed `/api/browser/tabs`, and wired chat tab_id reuse/binding.
- Phase 3: introduced `/api/overview` returning browser/doc/task/memory/storage stats for the home dashboard.
- Phase 4: `/api/repo/apply_patch` and `/run_checks` now run through change budgets, repo change logs, and the shared job ledger.
- Phase 5: bundle import/export expanded to browser history with dedup + tests, plus Chrome/Edge history import scaffolding.
- Phase 6: refresh worker jobs now mirror to the jobs table and `/api/jobs` allows status/type filtering for observability.
