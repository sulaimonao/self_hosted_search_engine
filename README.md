# Self-Hosted Search Engine

A fully local crawling + indexing stack powered by Scrapy, Whoosh, and Flask. Point the crawler at any site, rebuild the index, and search from the CLI or a lightweight web UI. No third-party APIs or hosted services required.

## Requirements

- Python 3.11.x (a `.python-version` file pins the project to 3.11.12)
- macOS or Linux with the system dependencies needed for Playwright's Chromium build
- (Optional) Node.js is **not** required

Verify your interpreter before creating the virtual environment:

```bash
./scripts/ensure_py311.sh python3
```

## Quick start

```bash
make setup            # creates .venv, installs deps, installs Playwright Chromium
make dev              # loads .env (if present) and starts the Flask dev server
# UI is available at http://127.0.0.1:5000
```

A quick smoke check is available too:

```bash
pytest -q
```

## RAG vector store configuration

The retrieval layer persists embeddings in a local [Chroma](https://www.trychroma.com/) store and tracks crawl metadata in DuckDB. Both paths are configurable via `config.yaml`:

| Setting | Default | Purpose |
| --- | --- | --- |
| `index.persist_dir` | `./.chroma` | Directory holding the Chroma collection used during retrieval |
| `index.db_path` | `./data/index.duckdb` | DuckDB database storing document metadata for crawl deduplication |

Ensure these locations live on fast local storage—the cold-start indexer and Flask app share the same files, so the vector store must be accessible to both processes.

## Crawl → Index → Search

Seed the crawler with either a single URL or a seeds file:

```bash
make crawl URL="https://www.vmware.com/"
# or
make crawl SEEDS_FILE="/path/to/seeds.txt"
```

The crawler writes raw responses and normalized text to `data/crawl/`. When raw data changes you can normalize and index incrementally:

```bash
make normalize
make reindex-incremental
make tail               # follow the focused crawl log in another terminal
```

### Index schema upgrades

The incremental indexer now validates the on-disk Whoosh schema before reusing it. If a legacy deployment only contains the
`text`, `title`, and `url` fields, the index directory is automatically rebuilt so the modern `url`, `lang`, `title`, `h1h2`, and
`body` fields are available. Existing postings are discarded during this migration, so plan to re-run your crawl or the
incremental indexer afterwards to repopulate the upgraded schema.

Run CLI searches straight from your terminal:

```bash
make search Q="VMware installation guide for macOS"
# or directly
python bin/search_cli.py --q "VMware installation guide for macOS" --limit 5
```

Open http://127.0.0.1:5000 in a browser for the minimal web UI. Results stream in via `fetch()` and render with highlighted snippets.

## Smart search enrichment

The `/search` endpoint now wraps the base Whoosh query with a "smart" layer. When fewer than `SMART_MIN_RESULTS` hits come back, the
app schedules `bin/crawl_focused.py` in the background and immediately returns the current results. The focused crawl:

- Builds deterministic candidates from `search/frontier.py` (docs/blog/support paths, readthedocs/gitbook fallbacks, etc.).
- Merges in the highest-scoring domains from the append-only `data/seeds.jsonl` store (managed by `search/seeds.py`).
- Optionally asks a local Ollama model for additional URLs through `llm/seed_guesser.py` when the UI toggle is on.
- Uses `FOCUSED_CRAWL_BUDGET` as its page limit so a background run stays lightweight.
- Records every touched domain back into `data/seeds.jsonl`, gradually improving future crawls.

Results in the browser update automatically: if the first response returned fewer than the configured minimum, the UI polls the
`/search` endpoint every four seconds (up to ~20 seconds) and re-renders as new hits arrive.

With the cold-start upgrades the pipeline no longer requires a manual `make crawl` kick-off. When the index is empty the first search request:

- Schedules a focused crawl using `python -m crawler.run` with the configured budget.
- Streams crawler logs to `data/logs/focused.log` and exposes them via `/api/focused/status`.
- Normalizes every newly fetched page with Trafilatura + language detection and incrementally indexes changed documents.
- Emits `last_index_time` so the browser can auto-refresh results as soon as new hits land.

You can tail progress from the CLI with `make tail` or fetch metrics from `/metrics` to verify crawl/index counters.

To trigger a run manually, supply a query via `make focused`:

```bash
make focused Q="postgres vacuum best practices" USE_LLM=1 MODEL="llama3.1:8b-instruct"
make tail
```

The command honours `.env`, allows a one-off `BUDGET=...` override, and respects `CRAWL_RESPECT_ROBOTS` unless you turn it off.

## LLM Assist panel

The web UI now includes an "LLM Assist" panel:

- The status row checks `ollama --version` and the Ollama HTTP API (`/api/tags`) to report whether the runtime is installed and
  reachable.
- A model dropdown lists locally available models. The selection is stored in `localStorage` and passed to the focused crawl.
- The "Use LLM for discovery" toggle persists in `localStorage` and controls whether `smart_search` adds the `--use-llm` flag.
- Inline guidance appears when Ollama is missing, stopped, or running without any pulled models.

Install and start Ollama locally (macOS example):

```bash
brew install --cask ollama
ollama serve
ollama pull llama3.1:8b-instruct
ollama pull nomic-embed-text
```

The embedding model used for semantic search lives in `config.yaml` under `models.embed`:

```yaml
models:
  llm_primary: "gemma2:latest"
  llm_fallback: "gpt-oss:latest"
  embed: "nomic-embed-text"
```

That `embed` entry is mandatory—without a pulled embedding model the Flask app logs a startup warning (`Ollama embedding model 'nomic-embed-text' unavailable …`) and every `/api/search` request returns HTTP 503 with an `embedding_unavailable` payload until the model is installed.

To switch to [EmbeddingGemma](https://ollama.com/library/embedding-gemma):

```bash
ollama pull embedding-gemma:latest
```

Then either edit `config.yaml` to set `models.embed: "embedding-gemma:latest"`, or add an environment override before starting the app:

```bash
export RAG_EMBED_MODEL_NAME=embedding-gemma:latest
make dev
```

Adding the override to `.env` works as well; the `app.py` loader reads it on boot. Once the embedding model is present and `ollama serve` is running, the warning disappears and `/api/search` responses return to `200`.

Then point your browser at the UI. You can verify connectivity via:

```bash
make llm-status   # reports installed/running/host
make llm-models   # lists models returned by /api/tags
```

The default behaviour stays fully local: no external APIs are contacted unless you explicitly enable Ollama. Set `SMART_USE_LLM=true`
in `.env` if you want the toggle pre-enabled for every user.

## Project layout

```
.
├── app.py                # Flask application with /, /search, /healthz
├── bin/
│   ├── crawl.py          # Scrapy wrapper (seeds, env vars, Playwright toggle)
│   ├── crawl_focused.py  # Query-driven focused crawl with small page budgets
│   ├── dev_check.py      # Ensures index/crawl dirs exist before dev server starts
│   ├── reindex.py        # Rebuilds the Whoosh index from normalized crawl data
│   └── search_cli.py     # Terminal search client with score + snippet output
├── llm/
│   ├── __init__.py
│   └── seed_guesser.py   # Lightweight Ollama client for seed guessing
├── crawler/
│   ├── pipelines.py      # Writes raw + normalized JSONL to data/crawl/
│   ├── seeds.txt         # Default seeds list (one URL per line)
│   ├── settings.py       # Scrapy settings factory (robots, concurrency, Playwright)
│   └── spiders/
│       └── generic_spider.py
├── search/
│   ├── frontier.py       # Deterministic candidate URL generation for focused crawls
│   ├── indexer.py        # create_or_open_index + JSONL ingestion helpers
│   ├── query.py          # Multifield Whoosh query utilities
│   ├── seeds.py          # Append-only JSONL store tracking useful domains
│   └── smart_search.py   # Wrapper that triggers focused crawls when results are sparse
├── static/style.css      # Clean, minimal styling for the web UI
├── templates/index.html  # Browser UI (search box + async results)
└── tests/test_health.py  # Smoke test for /healthz
```

## Environment variables

Export variables via `.env` (auto-loaded by `make` targets) or the shell:

| Variable | Default | Purpose |
| --- | --- | --- |
| `INDEX_DIR` | `./data/index` | Location of the Whoosh index |
| `CRAWL_STORE` | `./data/crawl` | Where crawler JSONL data is persisted |
| `CRAWL_MAX_PAGES` | `100` | Stop after visiting this many pages |
| `CRAWL_RESPECT_ROBOTS` | `true` | Toggle robots.txt compliance |
| `CRAWL_ALLOW_LIST` | _(empty)_ | Comma-separated substrings URLs must contain |
| `CRAWL_DENY_LIST` | _(empty)_ | Comma-separated substrings URLs must not contain |
| `CRAWL_USE_PLAYWRIGHT` | `auto` | `0` disables, `1` forces, `auto` re-renders JS-heavy pages |
| `CRAWL_DOWNLOAD_DELAY` | `0.25` | Delay between requests in seconds |
| `CRAWL_CONCURRENT_REQUESTS` | `8` | Global Scrapy concurrency |
| `CRAWL_CONCURRENT_PER_DOMAIN` | `4` | Per-domain concurrency cap |
| `SEARCH_DEFAULT_LIMIT` | `20` | Default number of web UI results |
| `SMART_MIN_RESULTS` | `1` | Minimum results before auto-triggering a focused crawl |
| `FOCUSED_CRAWL_ENABLED` | `1` | Enable the cold-start focused crawl pipeline |
| `FOCUSED_CRAWL_BUDGET` | `10` | Page budget for each focused crawl run |
| `SMART_TRIGGER_COOLDOWN` | `900` | Seconds to wait before re-running a crawl for the same query |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Base URL for the local Ollama API |
| `SMART_USE_LLM` | `false` | Default toggle for LLM-assisted discovery |
| `USE_LLM_RERANK` | `false` | Enable LLM reranking of the top N results |
| `SEED_QUOTA_NON_EN` | `0.30` | Minimum non-English share in curated seeds |
| `SEED_QUOTA_NON_US` | `0.40` | Minimum non-US share in curated seeds |
| `FRONTIER_W_VALUE` | `0.5` | Weight applied to value priors when ranking frontier URLs |
| `FRONTIER_W_FRESH` | `0.3` | Weight applied to freshness hints |
| `FRONTIER_W_AUTH` | `0.2` | Weight applied to host authority |
| `INDEX_INC_WINDOW_MIN` | `60` | Sliding window (minutes) for incremental reindex |
| `SEEDS_PATH` | `data/seeds.jsonl` | Append-only JSONL store of known helpful domains |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Base URL for the local Ollama API |
| `OLLAMA_MODEL` | `llama3.1:8b-instruct` | Default model used when the UI does not pick one |
| `OLLAMA_TIMEOUT` | `30` | Seconds to wait for Ollama seed generation responses |
| `LOG_LEVEL` | `INFO` | Logging level for the Flask app |

## Scripts & automation

- `make setup` – creates `.venv`, installs Python deps, installs Chromium via Playwright.
- `make dev` – loads `.env`, runs `bin/dev_check.py`, and starts the Flask dev server with auto-reload.
- `make crawl` – wraps `python bin/crawl.py`; accepts `URL`, `SEEDS_FILE`, and respects `.env` overrides.
- `make reindex` – rebuilds the Whoosh index (use `make index-inc` for incremental updates).
- `make search` – executes the CLI search client with optional `LIMIT`.
- `make focused` – runs `bin/crawl_focused.py` for a specific query (`Q="..."`) with optional `BUDGET`, `USE_LLM`, and `MODEL` overrides.
- `make llm-status` – quick health check for the Ollama HTTP API exposed through Flask.
- `make llm-models` – list locally installed Ollama models via the API.
- `pytest -q` – runs the smoke test hitting `/healthz`.

## Troubleshooting

- **“No seeds provided”** – pass `URL=...` to `make crawl` or populate `crawler/seeds.txt`.
- **Empty results** – confirm `data/crawl/normalized.jsonl` exists, then run `make reindex`.
- **Playwright prompts** – `make setup` installs Chromium automatically; re-run if browsers are missing.
- **Non-3.11 Python** – run `./scripts/ensure_py311.sh python3` before `make setup`.

## Cold-start & LLM enhancements

- `make seeds` generates `data/seeds/curated_seeds.jsonl` by merging local lists, CommonCrawl dumps, stored sitemaps, and (when enabled) Ollama suggestions. Domains are merged into `data/seeds.jsonl` with diversity quotas applied.
- `make index-inc` performs a single incremental indexing pass using the `INDEX_INC_WINDOW_MIN` sliding window. Run `bin/index_inc.py` without `--once` to keep indexing continuously.
- Focused crawls now prioritise seeds via value priors, freshness hints, and host authority metrics while avoiding duplicate URLs and content fingerprints.
- Optional LLM reranking (`USE_LLM_RERANK=1`) adjusts the top results. `/metrics` exposes coverage, freshness lag, focused trigger rates, enqueue counts, and LLM usage.

## Docker (optional)

The included Dockerfile + Compose definition build on Python 3.11. Update the bind mounts or environment variables if you want to persist data outside the container.
