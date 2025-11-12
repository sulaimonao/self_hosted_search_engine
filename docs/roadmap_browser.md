# Personal Search Engine → Browser: Roadmap

## Runtime & Config

- [x] Zero-touch dev UX (UI-discoverable/toggleable features; no file edits)
- [x] SQLite-backed runtime config loaded at backend startup
- [x] Health/capability/config/diagnostics/model-install REST endpoints
- [x] Relaxed autopull defaults for Gemma-3 / GPT-OSS
- [ ] UI surface for feature flags (Shadow, Agent, Local Discovery) instead of `.env`
- [~] Desktop parity: all web features in Electron

## UI / UX

- [x] Control Center panel (status, settings, toggles)
- [~] Status ribbon moved to bottom status bar (clickable)
- [x] First-run wizard (install models, health checks, defaults)
- [x] Browser shell navigation + Electron bridge
- [ ] Chat: “Use current page as context” control (restore)
- [~] Keep original chat design; fix logic only

## Chat & Agents

- [ ] “Reasoning” toggle (subscribe to agent logs)
- [ ] Browsing fallbacks: RSS → site search → homepage scrape
- [~] Reliable stream→UI render; no silent drops
- [x] Friendly model errors; fallback GPT-OSS ↔ Gemma-3

## Diagnostics & Testing

- [~] E2E diag: detect UI/API/browser/LLM link breaks (full-app)
- [ ] Repo-aware diag rules (globs for .ndjson/.sqlite3/*.log etc.)
- [ ] Smoke checks + `--fail-on` thresholds in Control Center
- [ ] Bootstrap fix for Python `tomllib` on <3.11
- [ ] Make/CI tasks: verify/test/lint/type (no servers in CI)

## Logging & Telemetry

- [x] Structured telemetry `events.ndjson` (+ `chat.stream_summary`)
- [x] Backend `backend.log`, frontend→backend logging pipeline (`LOG_DIR`)
- [x] In-app log viewer `/debug/logs` (polls `/api/logs/recent`)
- [x] Trace-aware telemetry (reload reason, step counts, dur_ms)
- [ ] Daily rotation, per-feature segmentation, `test_run_id`

## Models & Indexing

- [x] Local models only (Ollama: GPT-OSS primary, Gemma-3 fallback; EmbeddingGemma)
- [x] Model install/availability checks (wizard + Control Center)
- [ ] Index health widget (doc counts, last reindex, auto-rebuild corrupt)
- [ ] Domain “clearance” detectors (paywalls/login redirects)

## Stability & Fixes

- [~] Fix React “Maximum update depth exceeded” in chat flow
- [~] Hydration mismatch warnings in Next/Electron
- [~] Harden stream pipeline (server→client)
- [ ] Makefile/dev script target-pattern edge cases

Legend: [x]=Done, [~]=In Progress, [ ]=Planned
