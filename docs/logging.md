# Unified Logging Guide

This repository now exposes a shared logging surface across Electron, Next.js, and the Flask backend. The goals are
consistent correlation IDs, predictable rotation, and an export pipeline that produces LLM-ready JSONL bundles.

## Directory layout and rotation

All runtime logs default to the repo-level `logs/` directory when running in development. Packaged Electron builds
resolve the same path via `app.getPath('userData')/logs`, keeping end-user data in their profile directory.

```text
logs/
  app.log                  # rolling text log for Node/Electron contexts
  app-YYYY-MM-DD.log       # rotated Node/Electron text logs (daily)
  app-YYYY-MM-DD.jsonl     # structured JSONL export of the same data
  flask.log                # active Flask server log
  flask-YYYY-MM-DD.log     # rotated Flask logs
  flask-YYYY-MM-DD.jsonl   # structured Flask entries
  llm_exports/
    session-*.jsonl        # sanitized bundles for LLM analysis
```

Set `LOG_DIR=/custom/path` (and/or `LOG_LEVEL`) to override defaults for any service.

## Shared Winston logger (Node/Electron)

Use `shared/logger` anywhere you have access to Node APIs (Electron main, Next.js API routes, CLI scripts):

```ts
import logger from '@shared/logger';

const mainLogger = logger.child({ component: 'electron-main' });
mainLogger.info('Creating window', { target });

// Attach correlation IDs when handling a request
const requestLogger = mainLogger.child({ correlationId });
requestLogger.error('Unhandled stream failure', { stack: error.stack });
```

The module automatically:

- Resolves the correct log directory (Electron production builds write to `userData/logs`).
- Applies daily rotation (5 MB max, 14 days retained) for both text and JSONL files.
- Adds a JSONL transport so every log entry is one machine-readable line.
- Provides console colorized output when `NODE_ENV !== 'production'`.
- Hooks `process.on('unhandledRejection')` and `process.on('uncaughtException')` when a component registers handlers.

Helper exports:

- `createComponentLogger(component: string)` – convenience child logger with baked-in component metadata.
- `withCorrelationId(logger, correlationId)` – derive a child logger that always includes the supplied ID.
- `getLogDirectory()` – returns the resolved log directory at runtime.

## Next.js middleware and API logging

- `frontend/middleware.ts` assigns a UUID correlation ID to every `/api/*` request when the header is missing. The
  middleware writes the header to both the downstream request and the response.
- API routes (for example `src/app/api/chat/route.ts`) import the shared logger, log request start/end, and attach the
  correlation ID to all upstream fetch calls via `X-Correlation-Id`. All responses (including SSE/NDJSON streams)
  receive the ID in their headers.
- Global `process` handlers on the Next server surface unhandled errors through the shared logger.

When adding a new API route, follow the pattern used in `chat/route.ts`: generate or read the correlation ID, log start
and completion, wrap all `Response` objects via a helper that sets `x-correlation-id`, and propagate the header to
backend services.

Client-side error reporting already funnelled through `ErrorClientSetup` continues to post to `/api/logs` on the Flask
backend; those events show up in the same log files with `component: 'frontend'`.

## Flask backend logging

`backend/app/logging_setup.py` now configures:

- Timed rotating file handlers for `logs/flask.log` and `logs/flask-YYYY-MM-DD.log` (14-day retention).
- Matching JSONL handlers (`flask-YYYY-MM-DD.jsonl`) containing `timestamp`, `level`, `component`,
  `correlation_id`, `message`, optional `stack`, and `meta` payloads.
- A `CorrelationIdFilter` that injects `X-Correlation-Id` (or `g.trace_id`) onto every record.
- Request middleware (`backend/app/middleware/request_id.py`) that:
  - Honors incoming `X-Correlation-Id` headers.
  - Logs `HTTP METHOD PATH -> STATUS (duration)` summaries via `get_request_logger()`.
  - Propagates the correlation ID back to the client on every response.

Flask still emits structured traffic events via `log_inbound_http_traffic`, so existing telemetry consumers continue to
function.

## Exporting logs for LLMs

`scripts/export_logs_for_llm.py` aggregates `.log` and `.jsonl` files into a single sanitized JSONL bundle:

```bash
# From the repo root
python scripts/export_logs_for_llm.py
# or specify a custom directory
python scripts/export_logs_for_llm.py --logs-dir /path/to/logs --output-dir /tmp/exports
```

Features:

- Recursively scans the `logs/` tree (skipping `logs/llm_exports/`).
- Parses structured JSON lines directly and falls back to regex parsing for plain text entries.
- Normalizes fields into `{timestamp, level, component, correlation_id, message, stack?, meta?}`.
- Redacts obvious secrets (emails, bearer tokens, common API key patterns) and truncates long strings.
- Maintains chronological order, falling back to file order if a timestamp is missing.
- Writes `logs/llm_exports/session-YYYYMMDD-HHMMSS.jsonl` and prints the entry count.

:warning: **Safety reminder** – even after redaction, you are responsible for ensuring no sensitive data leaves your
machine. Review the generated bundle before uploading it to any third-party LLM or chatbot.

A sample file (`logs/llm_exports/sample-session.jsonl`) documents the final schema for tooling/tests.

## Quick reference

- Shared logger module: `shared/logger/index.js`
- Electron main processes: `desktop/main.ts`, `frontend/electron/main.js`
- Next.js middleware: `frontend/middleware.ts`
- Next.js chat API logging: `frontend/src/app/api/chat/route.ts`
- Flask configuration: `backend/app/logging_setup.py`, `backend/app/middleware/request_id.py`
- Export script: `scripts/export_logs_for_llm.py`

When adding new services, import the shared logger (for Node contexts) or extend the Flask setup so all logs keep the
same shape and correlation semantics.
