# Backend observability: tracing, SSE, and metrics

This note proposes small, low-risk improvements to standardize tracing across HTTP and SSE endpoints and to surface useful metrics for search reliability.

## Correlation IDs

- Accept and propagate X-Request-Id from clients; if missing, generate a request id early in the request lifecycle and attach to logs.
- Return the id in responses using one of:
  - X-Request-Id (preferred, widely used)
  - X-Trace-Id (alias, if already present in parts of the stack)
- For error JSON bodies, include a trace_id string field alongside code/message for easier user-facing surfacing.

Example error JSON:
{
  "ok": false,
  "code": "MODEL_NOT_FOUND",
  "message": "The requested model is not available.",
  "trace_id": "req_abc123"
}

## SSE and NDJSON streaming

- Include a trace_id field in an initial metadata frame and repeat it on each subsequent frame (so partial logs still correlate).
- For SSE (text/event-stream), add headers:
  - X-Request-Id: <trace_id>
  - Cache-Control: no-store
  - Content-Type: text/event-stream; charset=utf-8
  - Connection: keep-alive
- For NDJSON, include a metadata envelope as the first line, e.g.:
  {"type":"meta","trace_id":"req_abc123","model":"gpt-xyz"}

Per-event fields to consider repeating:

- trace_id (string)
- ts (ISO timestamp)
- type (e.g., meta, chunk, error, done)
- model (if applicable)
- usage tokens (when known)

## Search metrics and provenance

- Emit counters/timers for:
  - search.hybrid.ok / .error
  - search.keyword.ok / .error
  - search.legacy.ok / .error
  - search.hybrid.duration_ms, search.keyword.duration_ms
  - search.hybrid.fallback_to_keyword (boolean or counter)
- Attach provenance in JSON results: source: "hybrid" | "keyword" | "legacy" and include trace_id.

## Error normalization

- Normalize common errors to stable codes with HTTP 4xx where applicable:
  - model_not_found → 400 MODEL_NOT_FOUND
  - empty_input → 400 EMPTY_MESSAGE
  - upstream_timeout → 504 UPSTREAM_TIMEOUT
  - upstream_error → 502 UPSTREAM_ERROR
- Always include message and trace_id.

## Log shape (server)

Log a single structured line per request with fields:

- trace_id, method, path, status, duration_ms, user_agent, remote_addr
- error_code (when set), error_message (short), model (if relevant)
- For streaming, log start and end records using the same trace_id.

## Rollout tips

- Start by adding header passthrough and response headers.
- Add metadata frames to streaming responses next.
- Backfill error JSONs with trace_id and code.
- Document in API reference and keep codes stable.
