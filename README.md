# Self-Hosted Search Engine

A fully local crawling, indexing, and research stack powered by Scrapy, Whoosh,
Chroma, and Flask. Point the crawler at any site, rebuild the index, and search
from the CLI or the modern web UI—no hosted services or third-party APIs
required.

## Table of contents

- [Stack overview](#stack-overview)
- [Requirements](#requirements)
- [Initial setup](#initial-setup)
- [Running the application](#running-the-application)
- [Command quick reference](#command-quick-reference)
- [Data & storage layout](#data--storage-layout)
- [Testing & quality gates](#testing--quality-gates)
- [Observability & debugging](#observability--debugging)
- [API surface](#api-surface)
- [Discovery & enrichment flows](#discovery--enrichment-flows)
- [LLM integration](#llm-integration)
- [Diagnostics snapshot API](#diagnostics-snapshot-api)

## Stack overview

```
frontend/        Next.js copilot UI (App Router, Tailwind 4, shadcn/ui)
server/          Flask API surface and orchestration logic
backend/         Index builders, retrieval, and CLI utilities
crawler/         Focused crawler (Scrapy) + URL frontier
engine/          Search pipelines (Whoosh BM25 + vector reranker)
llm/             Ollama helpers for discovery, planning, and embeddings
scripts/         Local tooling (change budget guard, telemetry tail, etc.)
seeds/           Curated discovery registry (`docs/registry_structure.md`)
static/, templates/   Assets served by Flask
```

Supporting assets live under `data/` at runtime. The directory is safe to delete
while the services are stopped; the next boot will recreate it as needed.

## Requirements

- Python **3.11.x** (pinned via `.python-version` to 3.11.12)
- macOS or Linux capable of running Playwright's Chromium build
- Node.js **18+** (Node 20+ recommended) for the frontend dev server
- npm (bundled with Node.js)
- Optional: [Ollama](https://ollama.com/) for LLM-assisted discovery and chat

Verify the interpreter that will back your virtual environment before running
`make setup`:

```bash
./scripts/ensure_py311.sh python3
```

## Initial setup

1. **Clone** the repository and `cd` into it.
2. **Create a virtual environment** and install the Python packages plus the
   editable package:

   ```bash
   make setup
   ```

   The target installs backend dependencies, Playwright Chromium, and runs a
   quick import check.
3. **Install frontend dependencies** (done automatically by `make dev`, but you
   can pre-install):

   ```bash
   cd frontend
   npm install
   cd ..
   ```
4. **Configure environment overrides (optional)** by copying `.env.example`:

   ```bash
   cp .env.example .env
   ```

   The file exposes common knobs such as Flask host/port, Ollama endpoint,
   telemetry locations, agent limits, and the CORS origin (`FRONTEND_ORIGIN`).
   Any values left unset fall back to sensible defaults baked into the Make
   targets. When the frontend runs on a different hostname (or via HTTPS),
   update `FRONTEND_ORIGIN` so API responses include the matching
   `Access-Control-Allow-*` headers.

5. **Inspect repository paths** at any time with:

   ```bash
   make paths
   ```

## Running the application

### One-command development stack

The recommended workflow launches both the Flask API and the Next.js frontend in
one terminal:

```bash
make dev
```

`make dev` performs the following:

- Loads `.env` (if present) to populate environment variables.
- Starts the Flask server (default `http://127.0.0.1:5050`; overrides via
  `UI_PORT` or `FLASK_RUN_PORT`).
- Boots the Next.js dev server (default `http://127.0.0.1:3100`; override with
  `FRONTEND_PORT`).
- Exposes the API base URL to the frontend via `NEXT_PUBLIC_API_BASE_URL`.
- Publishes the browser origin to the Flask API via `FRONTEND_ORIGIN` for CORS.
- Shuts everything down gracefully when you hit <kbd>Ctrl</kbd> + <kbd>C</kbd>,
  even when one process exits early.

Open the browser at `http://127.0.0.1:3100` to use the UI. If `127.0.0.1:5050`
is busy (macOS ships AirPlay on that port), set `UI_PORT=5051 make dev` instead.
The Flask server also serves a minimal UI at its root when you prefer not to run
the Next.js app.

### Backend or frontend individually

Run just the Flask backend (using the existing `.venv`) with hot reload:

```bash
make run
```

Launch the frontend in a separate terminal (remember to export
`NEXT_PUBLIC_API_BASE_URL` when pointing at a remote API):

```bash
cd frontend
npm run dev -- --hostname 0.0.0.0 --port 3100
```

### Crawling, indexing, and searching

Once the stack is running you can drive the full crawl → normalize → index →
search pipeline entirely from the CLI:

```bash
make crawl URL="https://example.com/"   # polite crawl with dedupe metadata
make normalize                           # normalize newly crawled pages
make reindex-incremental                 # embed + upsert changed docs
make search Q="example setup guide"      # BM25 + vector blended retrieval
```

Set `SEEDS_FILE=/path/to/seeds.txt` when seeding the crawler from a curated URL
list instead of a single entrypoint.

## Command quick reference

| Command | Purpose |
| --- | --- |
| `make setup` | Create `.venv`, install Python deps, install Playwright Chromium |
| `make dev` | Launch Flask + Next.js together with shared environment |
| `make run` | Run the Flask backend only (respects `.env`) |
| `make crawl` | Crawl a URL or seeds file into `data/crawl/` |
| `make normalize` | Convert raw crawl output into normalized JSON lines |
| `make reindex-incremental` | Embed and upsert changed documents into the vector store |
| `make search Q="..."` | Execute a blended CLI search (BM25 + vectors) |
| `make focused Q="..."` | Run the focused crawler for a query (LLM optional) |
| `make llm-status` | Check Ollama reachability via the Flask API |
| `make llm-models` | List chat-capable models reported by Ollama |
| `make tail JOB=focused` | Tail `data/logs/<JOB>.log` (e.g. focused crawl logs) |
| `make check` | Run linting, typing, tests, security, and performance smoke |
| `make clean` | Remove `.venv` and cached data stores |

Use `make help` for the full phony target list (inspect the `Makefile` for more
advanced flows such as `research` or `index-inc`).

## Data & storage layout

Runtime artefacts live under `data/`:

| Path | Purpose |
| --- | --- |
| `data/crawl/` | Raw crawler outputs (HTML, metadata) |
| `data/normalized/normalized.jsonl` | Normalized text documents ready for indexing |
| `data/whoosh/` | On-disk Whoosh BM25 index |
| `data/chroma/` | Local Chroma vector store for embeddings |
| `data/index.duckdb` | DuckDB metadata used for dedupe and incremental indexing |
| `data/agent/` | Planner artefacts (`frontier.sqlite3`, `documents/`, `vector_store/`) |
| `data/logs/` | Log files (e.g. `focused.log`, diagnostics snapshots) |
| `data/telemetry/` | Structured JSON telemetry written by the Flask API |

Override any of these paths through `.env` or by exporting variables before
invoking the relevant Make target (see `Makefile` for the full list). Fast local
storage is strongly recommended because the Flask app and background workers
share the same directories.

## Testing & quality gates

The repository ships with an opinionated pre-flight suite. Run it before opening
pull requests:

```bash
make check
```

`make check` executes:

1. `pytest -q` – unit, API, and e2e coverage (including
   `tests/e2e/test_agent_improves_answer.py`).
2. `ruff check` – linting across the maintainer surface (`server`, `scripts`,
   `policy`).
3. `black --check` – formatting guard for select modules.
4. `mypy` – static type analysis (ignoring external stubs).
5. `pip-audit` – dependency vulnerability scan (allowed to warn without failing).
6. `bandit` – security lint for the maintainer entrypoints.
7. `python scripts/perf_smoke.py` – lightweight performance regression check.

For iterative work, a quick smoke test is usually enough:

```bash
pytest -q
```

The change-budget guard (`python scripts/change_budget.py`) enforces ≤10 files
and ≤500 lines of churn for autonomous agents. Invoke it manually to validate
local diffs before committing.

## Observability & debugging

Structured telemetry is written to newline-delimited JSON under
`data/telemetry/events.ndjson`. Tune the location with `LOG_DIR` and the maximum
field length via `LOG_MAX_FIELD_BYTES`. Follow live events with:

```bash
./scripts/tail_telemetry.sh
```

Every Flask request emits `req.start` / `req.end` events with request, session,
and user correlation IDs. Tool invocations emit
`tool.start` / `tool.end` / `tool.error` events with redacted inputs and result
previews. Planner responses append `agent.turn` summaries, and API responses
include a `run_log` array so the UI can surface per-turn activity.

Inspect the learned discovery database at any time:

```bash
sqlite3 data/learned_web.sqlite3 \
  "SELECT query, url, reason, score FROM discoveries ORDER BY discovered_at DESC LIMIT 5;"
```

Focus crawl logs stream to `data/logs/focused.log`. Tail them with
`make tail JOB=focused` while a crawl is active.

## API surface

Key endpoints (all under `/api/` unless otherwise noted):

| Endpoint | Description |
| --- | --- |
| `POST /api/tools/search_index` | Blend vector + BM25 retrieval, falling back to BM25 when embeddings are unavailable. |
| `POST /api/tools/enqueue_crawl` | Queue pages for polite background crawling with dedupe metadata (`topic`, `reason`, `source_task_id`). |
| `POST /api/tools/fetch_page` | Fetch and normalize a single page, storing it under `data/agent/documents/`. |
| `POST /api/tools/reindex` | Incrementally embed + upsert changed documents into the agent vector store (`data/agent/vector_store/`). |
| `GET /api/tools/status` | Return counters for the frontier queue and vector store. |
| `POST /api/tools/agent/turn` | Run the full policy loop (search → fetch ≤3 pages → reindex → synthesize answer with citations). |
| `POST /api/refresh` | Trigger a focused crawl for the supplied query and optional LLM model override. |
| `GET /api/refresh/status` | Report background crawl state (`queued`, `crawling`, `indexing`) plus counters. |
| `GET /api/llm/status` | Report Ollama installation status, reachability, and active host. |
| `GET /api/llm/models` | List locally available chat-capable Ollama models. |
| `POST /api/diagnostics` | Capture repository + runtime snapshot for debugging. |

The agent persists its planning artefacts in `data/agent/`:

- `frontier.sqlite3` stores the crawl queue with `source_task_id`, `topic`, and
  `reason` columns.
- `documents/` holds normalized JSON captures keyed by URL hash.
- `vector_store/` maintains `index.json` + `embeddings.npy` for semantic
  retrieval.

## Discovery & enrichment flows

### Smart search enrichment

The `/search` endpoint now wraps the base Whoosh query with a smart layer. When
fewer than `SMART_MIN_RESULTS` hits return, the app schedules the focused crawl
(`bin/crawl_focused.py`) in the background and immediately responds with the
current results. The focused crawl:

- Builds deterministic candidates from `search/frontier.py` (docs/blog/support
  paths, Read the Docs/GitBook fallbacks, etc.).
- Merges in the highest-scoring domains from the append-only
  `data/seeds.jsonl` store (managed by `search/seeds.py`).
- Optionally asks a local Ollama model for additional URLs through
  `llm/seed_guesser.py` when the UI toggle is on.
- Uses `FOCUSED_CRAWL_BUDGET` as its page limit so a background run stays
  lightweight.
- Records every touched domain back into `data/seeds.jsonl`, gradually improving
  future crawls.

Browser results update automatically: if the initial response returned fewer
than the configured minimum, the UI polls `/search` every four seconds (for ~20
seconds) and re-renders as new hits land.

### Cold-start discovery flow

With the cold-start upgrades the pipeline no longer requires a manual
`make crawl` kick-off. When the index is empty, the first search request:

1. Schedules a focused crawl using `python -m crawler.run` with the configured
   budget.
2. Streams crawler logs to `data/logs/focused.log` and exposes them via
   `/api/focused/status`.
3. Normalizes every newly fetched page with Trafilatura + language detection and
   incrementally indexes changed documents.
4. Emits `last_index_time` so the browser can auto-refresh as new hits land.

`server.discover.DiscoveryEngine` orchestrates this bootstrap. Each time a query
triggers the flow the engine:

- Loads curated registry entries (`seeds/registry.yaml`) and previously learned
  domain hints from `data/learned_web.sqlite3`.
- Adds optional LLM plans from `llm/seed_guesser.py` when the **Use LLM for
  discovery** toggle is on.
- Calls `DiscoveryEngine.discover()` to score and rank `crawler.frontier.Candidate`
  objects, automatically falling back to the registry frontier instead of
  Wikipedia.
- Walks each candidate through the crawler → chunker → embedder pipeline and
  writes embeddings into the vector store.
- Persists the discovery metadata (query, URL, source, score) so subsequent
  searches can reuse the same domains without a fresh crawl.

### Manual refresh controls

Trigger a focused crawl on demand by clicking **Refresh now** in the web UI. The
button lives under the status banner and:

- Calls `POST /api/refresh` with the current query, LLM toggle, and optional
  model override.
- Streams progress from the background worker (`queued → crawling → indexing`)
  into a compact progress bar.
- Unlocks once the run finishes so you can retry with a different prompt.

The same API is available for automation:

```bash
curl -X POST http://127.0.0.1:5000/api/refresh \
  -H 'Content-Type: application/json' \
  -d '{"query": "postgres vacuum best practices", "use_llm": true, "model": "llama3.1:8b-instruct"}'

curl "http://127.0.0.1:5000/api/refresh/status?job_id=<hex>&query=postgres%20vacuum%20best%20practices"
```

`POST` returns `{ job_id, status, created }` so callers can deduplicate
concurrent requests. `GET` yields the current snapshot (`state`, `progress`, and
counters for seeds/pages/docs). When no `job_id` is supplied the endpoint falls
back to the most recent run for the supplied query or lists active jobs.

Invoke the same functionality from the CLI:

```bash
make focused Q="postgres vacuum best practices" USE_LLM=1 MODEL="llama3.1:8b-instruct"
make tail JOB=focused
```

The command honours `.env`, allows a one-off `BUDGET=...` override, and respects
`CRAWL_RESPECT_ROBOTS` unless you disable it.

## LLM integration

### LLM Assist panel

The Next.js UI includes an **LLM Assist** panel that:

- Checks `ollama --version` and `GET /api/tags` to report whether the runtime is
  installed and reachable.
- Lists locally available chat-capable models (embedding-only entries are
  hidden). The selection is stored in `localStorage` and passed to the focused
  crawl.
- Provides inline guidance when Ollama is missing, stopped, or running without
  pulled models.

Install and start Ollama locally (macOS example):

```bash
brew install --cask ollama
ollama serve
ollama pull llama3.1:8b-instruct
```

### Embedding model defaults

- The backend defaults to the `embeddinggemma` model. On the first semantic
  search the Flask API checks whether the model exists locally, streams
  `ollama pull` progress to the UI, and queues concurrent queries until
  embeddings are available.
- Pull models manually if you prefer:

  ```bash
  ollama pull embeddinggemma
  ```

- Configure overrides with environment variables:
  - `EMBED_MODEL` – embedding model name (defaults to `embeddinggemma`).
  - `EMBED_AUTO_INSTALL` – set to `false` to disable automatic pulls.
  - `EMBED_FALLBACKS` – comma-separated fallback models
    (`nomic-embed-text,gte-small` by default).

Troubleshooting tips when auto-install stalls:

- **Disk space** – ensure Ollama has several GB free. Remove older models with
  `ollama rm <name>` if pulls fail with `no space left on device`.
- **Network stalls** – verify the host can reach `https://registry.ollama.ai`.
  The UI exposes a retry button and fallback picker, or you can pre-download the
  model into the Ollama cache.
- **Runtime offline** – the “Start Ollama” button issues
  `brew services start ollama` / `systemctl start ollama` depending on the
  platform and surfaces errors when the daemon remains offline.

Once embeddings are available and `ollama serve` is running, `/api/search`
responses return `200` and repeat queries reuse the cached vectors immediately.

Verify connectivity via the Make targets:

```bash
make llm-status
make llm-models
```

The default behaviour stays fully local: no external APIs are contacted unless
Ollama is enabled. Set `SMART_USE_LLM=true` in `.env` if you want the toggle
pre-enabled for every user.

### Planner LLM fallback

- `models.llm_primary` in `config.yaml` selects the planner's primary Ollama
  model.
- `models.llm_fallback` defines an optional backup used when the primary returns
  `404` / `model not found`.
- Pull at least one model locally (`ollama pull gpt-oss:20b`,
  `ollama pull gemma3:27b`, etc.).
- When both models are missing the planner responds with
  `{ "type": "final", "answer": "Planner LLM is unavailable." }` so the UI can
  degrade gracefully.

## Diagnostics snapshot API

Operators can capture the current repository state and runtime logs without
leaving the browser. `POST /api/diagnostics` enqueues a background job and
returns `{ "job_id": "<hex>" }`. Poll `/api/jobs/<job_id>/status` until `state`
becomes `done`; the `result` payload contains:

- `summary_markdown` – rendered report with git metadata, dependency versions,
  and log excerpts.
- `summary_path` – on-disk markdown file under `data/logs/diagnostics/` that can
  be downloaded for full context.
- Structured fields for git status, dependency snapshots, and the optional
  `pytest --collect-only` run.

Toggle expensive steps through environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DIAGNOSTICS_RUN_PYTEST` | `false` | Enable `pytest --collect-only -q` inside the diagnostics job (override per-request with `{ "include_pytest": true }`). |
| `DIAGNOSTICS_PYTEST_ARGS` | *(empty)* | Extra CLI arguments appended to the pytest collect command. |
| `DIAGNOSTICS_CMD_TIMEOUT` | `60` | Seconds before git/pytest/pip commands are aborted. |
| `DIAGNOSTICS_LOG_FILES` | `3` | Number of recent `*.log` files to sample from `data/logs`. |
| `DIAGNOSTICS_LOG_LINES` | `40` | Tail length captured for each sampled log file. |

Example macOS workflow:

```bash
source .venv/bin/activate
curl -X POST http://127.0.0.1:5000/api/diagnostics \
     -H 'Content-Type: application/json' \
     -d '{"include_pytest": true}'
# => {"job_id":"abc123..."}
curl http://127.0.0.1:5000/api/jobs/abc123.../status | jq .result.summary_path
```

## Continuous integration

GitHub Actions runs `make check` on Python 3.11 and enforces the same change
budget guard used locally. Linting covers Ruff, Black (check mode), and Mypy for
the maintainer surface; pytest exercises the full suite; `pip-audit` and Bandit
scan the policy-limited paths. The guard fails the build if a staged diff exceeds
50 files or 4,000 lines.

Maintainer autonomy defaults to **Observe** (read-only). Promote to **Patch** to
allow applying a diff after every gate passes. **Maintainer** unlocks multi-file
refactors while still respecting the budgets enforced by `policy/allowlist.yml`.
Regardless of autonomy level, always plan → patch → verify → document risks and
rollback steps before opening a PR.
