# Agent trace toggle, browsing fallbacks, index health, and domain clearance

This release adds four capabilities that work together to make the self-hosted
search engine easier to observe and recover:

- **Agent traces** surface tool usage metadata (no raw LLM reasoning) over a
  Server-Sent Events (SSE) channel. Frontend users can enable the trace stream
  with the *Show agent steps* toggle; the preference persists in
  `localStorage`.
- **Browsing fallbacks** ensure every `open URL` / crawler request returns a
  structured response. The fetch plan checks RSS/Atom feeds first, then common
  site-search endpoints, and finally scrapes the homepage for articles or nav
  links. Each attempt records the active strategy and diagnostics so UI and
  agents can degrade gracefully.
- **Index health** exposes lightweight probes for every storage backend, a
  last-success timestamp, and an asynchronous rebuild endpoint. The desktop UI
  now shows a badge in the browser status bar and a detailed panel with
  per-store metrics plus a rebuild control.
- **Domain clearance profiles** detect paywalls, login redirects, and common
  anti-bot interstitials whenever crawler fetches complete. The signals are
  stored in a SQLite table and exposed through `/api/domain_profiles` for fast
  lookups.

## Quick reference

| Feature | Backend entry point | Frontend surface | CLI helper |
| --- | --- | --- | --- |
| Agent trace SSE | `backend/app/api/agent_logs.py` (`/api/agent/logs`) | `ReasoningToggle`, `AgentTracePanel` | — |
| Browsing fallback | `backend/app/services/fallbacks.py` (`/api/browser/fallback`) | `AgentLogPanel` discovery list | — |
| Index health | `backend/app/services/index_health.py` (`/api/index/health`, `/api/index/rebuild`) | `IndexHealthBadge` & panel | `make index-health`, `make index-rebuild` |
| Domain clearance | `backend/app/services/auth_clearance.py`, `backend/app/db/domain_profiles.py` | — | — |

### Agent traces

- `backend/app/services/agent_tracing.py` redacts sensitive arguments and
  publishes normalized steps to a process-local `AgentLogBus`.
- `/api/agent/logs?chat_id=…` streams JSON events to the UI. The endpoint only
  forwards `type="agent_step"` payloads.
- `frontend/src/state/ui.ts` and `frontend/src/state/agentTrace.ts` coordinate
  the toggle state, SSE subscription, and per-message trace rendering.

### Browsing fallback chain

- `SmartFetcher` executes feed discovery, site search, and homepage scraping in
  order, returning the first strategy that yields items. Each step includes
  simple heuristics and guards to avoid infinite redirects.
- `/api/browser/fallback` wraps `smart_fetch` so that the desktop UI can fetch
  suggestions on demand.

### Index health

- `probe_all()` inspects SQLite, DuckDB, Whoosh, and vector backends; metadata
  for additional stores can be added in one place.
- Rebuild requests spin off a background thread that reloads keyword and vector
  indexes and updates the last-success marker.
- Frontend components fetch `/api/index/health` on mount and after rebuilds to
  keep the badge and panel in sync.

### Domain clearance profiles

- `detect_clearance()` inspects responses for paywall vendor signatures, login
  redirects, and anti-bot hints. Matches are written to a dedicated
  `domain_profiles` SQLite table.
- `/api/domain_profiles` exposes both list and single-domain lookups. Agents
  can consult this endpoint to avoid loops on paywalled or gated domains.

### Testing

- Python unit tests live in `tests/backend/test_*.py` and cover fallbacks,
  index probes, and auth clearance signals.
- Frontend tests in `frontend/src/state/__tests__/ui.test.tsx` verify the
  persistence toggle and trace rendering pipeline.

### Diagnostics

`tools/e2e_diag.py` loads the new probes to ensure all four features stay in
place during future refactors. Run `python3 tools/e2e_diag.py` to confirm the
full suite remains green.
