Frontend logging → backend telemetry
===================================

Overview
--------

The frontend (Next.js / Electron) forwards client-side instrumentation and errors into the centralized backend telemetry pipeline. Persisted telemetry lives in:

- data/telemetry/events.ndjson — newline-delimited JSON of structured events
- logs/backend.log — rotating plain-text backend log for human inspection

How the flow works
------------------

1. Renderer code calls `sendUiLog(evt)` (a lightweight helper).

   - In the desktop Electron environment the preload bridge exposes `window.appLogger.log()` which forwards directly to the backend process.
   - In a browser or normal Next.js environment `sendUiLog` POSTs to `POST /api/logs` on the backend.

2. The backend `POST /api/logs` endpoint validates and redacts the payload and funnels it into the same telemetry writer used by server-side logging.

   - The backend emits structured events using `backend.logging_utils.write_event(...)`.
   - Events are written as NDJSON to `data/telemetry/events.ndjson` and are optionally forwarded to OTLP/OpenTelemetry if configured.

3. All events include standardized fields (`event`, `level`, `msg`, `ts`, `meta`, etc.) so downstream tools or scripts can filter and analyze them.

Files of interest
-----------------

- frontend helper: `frontend/src/lib/logging.ts` — `sendUiLog(evt)` implementation
- Electron preload (desktop): `desktop/preload.ts` — exposes `window.appLogger.log` that forwards to backend
- Backend ingestion: `backend/app` (route `/api/logs` in `backend/app/__init__.py`)
- Structured writer: `backend/logging_utils.py` and `server/json_logger.py`
- Backend logging setup: `backend/app/logging_setup.py` (configures console, rotating file, and the structured telemetry handler)

Environment variables and configuration
---------------------------------------

- `LOG_DIR` — directory used by the backend structured writer (default: `data/telemetry`). The NDJSON file path is `LOG_DIR/events.ndjson`.
- `LOG_LEVEL` — backend log level (e.g. `INFO`, `DEBUG`).
- OTEL (optional): set `OTEL_EXPORTER_OTLP_ENDPOINT` and related env vars to forward spans/telemetry to an OTLP collector.
- `BACKEND_URL` or `API_URL` — used by frontend/electron to locate the backend for `/api/logs`.

Quick verification
------------------

1. Start the backend and frontend (desktop or dev server).

2. Trigger a client error in the renderer (DevTools):

   ```js
   throw new Error('test frontend error')
   ```

   or

   ```js
   Promise.reject(new Error('test rejection'))
   ```

3. Tail the events file:

   ```bash
   tail -f data/telemetry/events.ndjson
   # or, if you set LOG_DIR explicitly:
   tail -f $LOG_DIR/events.ndjson
   ```

   Look for events with `event` like `ui.error.window`, `ui.error.unhandledrejection`, or `ui.error.boundary`.

Tips and next steps
-------------------

- Add a small UI page to stream or filter `events.ndjson` for quick debugging.
- Add rate-limiting on `/api/logs` if you anticipate noisy clients.
- Consider transforming events into a compact schema for long-term storage or exporting to a log analysis platform.

