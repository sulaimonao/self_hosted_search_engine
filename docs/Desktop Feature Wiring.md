# Desktop Feature Wiring

The desktop shell wraps the Next.js UI and connects it to the local Flask backend
running on `127.0.0.1:5050`. This document describes the feature wiring required
for the desktop experience.

## API proxy

* The Next.js runtime rewrites `/api/*` requests to `http://127.0.0.1:5050/api/*`.
  The rewrite keeps `NEXT_PUBLIC_API_BASE_URL` support for overrides, but defaults
  to the local backend.

## Feature detection

* On boot the desktop page pings `/api/meta/server_time` (falling back to
  `/api/meta/time`) and `/api/llm/health`. The results update the shared Zustand
  store so UI elements can gray out when the backend is offline.
* Autopilot preferences and LLM model selection persist in `localStorage` so
  toggles survive restarts.

## LLM model selector

* `ModelPicker` loads `/api/llm/llm_models` and renders a dropdown of chat models.
  The selected value updates the shared store and persists to
  `localStorage` (`shipit:model`).
* Health checks hit `/api/llm/health` via SWR, and the badge reflects reachability
  and model counts.

## Local search panel

* Queries POST to `/api/index/hybrid_search` with a fallback to
  `/api/index/search` when hybrid search is unavailable. Hybrid results normalize
  to a single hits array so the panel can render both vector and keyword matches.

## Diagnostics

* `/shipit/diagnostics` invokes `POST /api/diagnostics`, pretty prints the JSON
  payload, and links any returned artifacts for quick download.

## Progress streaming

* Job progress uses `EventSource` against `/api/progress/<job_id>/stream` with a
  polling fallback when SSE is not available.
* Discovery subscriptions consume `/api/discovery/stream_events` and fall back to
  the legacy `/api/discovery/events` endpoint when necessary.

## Autopilot

* The main workspace exposes an "Autopilot follow-ups" toggle in settings and the
  desktop header mirrors the setting. When disabled, autopilot directives are
  logged but not executed.

## Tests

* Lightweight Vitest coverage lives under `frontend/src/app/shipit/lib/__tests__`
  and covers model inventory fetching, hybrid search fallback, diagnostics calls,
  and SSE wiring.
