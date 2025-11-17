# Backend Phases Progress

| Phase | Status           | Notes |
|-------|------------------|-------|
| 0     | Backend v1 Ready | `docs/backend_phase0_summary.md` documents the frozen stack and topology assumptions. |
| 1     | Backend v1 Ready | HydraFlow schema/migrations/APIs/chat wiring are stable and covered by bundle/import/export + privacy paths. |
| 2     | Backend v1 Ready | Tabs ↔ threads ↔ history bindings plus privacy deletes are hardened and documented for single-user data dirs. |
| 3     | Backend v1 Ready | `/api/overview` now ships the `{ok, data}` envelope and cached storage stats; ready for desktop dashboard consumers. |
| 4     | Backend v1 Ready | Repo tooling (`/propose_patch`, `/apply_patch`, `/run_checks`) enforces budgets + sandboxing and records repo/job ledgers. |
| 5     | Backend v1 Ready | Bundles round-trip threads/messages/tasks/history with manifest dedupe, import/export jobs, and regression tests. |
| 6     | Backend v1 Ready | Jobs ledger covers refresh/bundle/repo activity, pruning, and contract-shape regressions for `/api/jobs`. |
| 7     | Backend v1 Ready | Architecture/contracts docs are frozen for Backend v1; extension points + identity guidance unblock frontend integration. |

## Run Notes
- Initialized tracker.
- Phase 1: added llm_threads/messages/tasks/events/memory migrations, APIs, and chat persistence.
- Phase 2: linked tabs to threads/history metadata, exposed `/api/browser/tabs`, and wired chat tab_id reuse/binding.
- Phase 3: introduced `/api/overview` returning browser/doc/task/memory/storage stats for the home dashboard (now cached for perf and wrapped in the `{ok, data}` envelope).
- Phase 4: `/api/repo/apply_patch` and `/run_checks` now run through change budgets, repo change logs, strict path/command validation, and the shared job ledger.
- Phase 5: bundle import/export expanded to browser history with dedup + tests, plus Chrome/Edge history import scaffolding.
- Phase 6: refresh worker jobs mirror to the jobs table; `/api/jobs` allows status/type filtering and pruning for observability.
- Backend Contracts v1 are frozen for frontend integration; future changes require explicit versioning.
- System ready for frontend redesigns to consume the stabilized APIs/tests.
