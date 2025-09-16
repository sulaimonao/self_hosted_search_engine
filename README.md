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

## Crawl → Index → Search

Seed the crawler with either a single URL or a seeds file:

```bash
make crawl URL="https://www.vmware.com/"
# or
make crawl SEEDS_FILE="/path/to/seeds.txt"
```

The crawler writes raw responses and normalized text to `data/crawl/`. Once you have data, rebuild the index:

```bash
make reindex
```

Run CLI searches straight from your terminal:

```bash
make search Q="VMware installation guide for macOS"
# or directly
python bin/search_cli.py --q "VMware installation guide for macOS" --limit 5
```

Open http://127.0.0.1:5000 in a browser for the minimal web UI. Results stream in via `fetch()` and render with highlighted snippets.

## Project layout

```
.
├── app.py                # Flask application with /, /search, /healthz
├── bin/
│   ├── crawl.py          # Scrapy wrapper (seeds, env vars, Playwright toggle)
│   ├── dev_check.py      # Ensures index/crawl dirs exist before dev server starts
│   ├── reindex.py        # Rebuilds the Whoosh index from normalized crawl data
│   └── search_cli.py     # Terminal search client with score + snippet output
├── crawler/
│   ├── pipelines.py      # Writes raw + normalized JSONL to data/crawl/
│   ├── seeds.txt         # Default seeds list (one URL per line)
│   ├── settings.py       # Scrapy settings factory (robots, concurrency, Playwright)
│   └── spiders/
│       └── generic_spider.py
├── search/
│   ├── indexer.py        # create_or_open_index + JSONL ingestion helpers
│   └── query.py          # Multifield Whoosh query utilities
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
| `CRAWL_USE_PLAYWRIGHT` | `false` | Render every page with Playwright (JS-heavy sites) |
| `CRAWL_DOWNLOAD_DELAY` | `0.25` | Delay between requests in seconds |
| `CRAWL_CONCURRENT_REQUESTS` | `8` | Global Scrapy concurrency |
| `CRAWL_CONCURRENT_PER_DOMAIN` | `4` | Per-domain concurrency cap |
| `SEARCH_DEFAULT_LIMIT` | `20` | Default number of web UI results |
| `LOG_LEVEL` | `INFO` | Logging level for the Flask app |

## Scripts & automation

- `make setup` – creates `.venv`, installs Python deps, installs Chromium via Playwright.
- `make dev` – loads `.env`, runs `bin/dev_check.py`, and starts the Flask dev server with auto-reload.
- `make crawl` – wraps `python bin/crawl.py`; accepts `URL`, `SEEDS_FILE`, and respects `.env` overrides.
- `make reindex` – wipes and rebuilds the Whoosh index from `data/crawl/normalized.jsonl`.
- `make search` – executes the CLI search client with optional `LIMIT`.
- `pytest -q` – runs the smoke test hitting `/healthz`.

## Troubleshooting

- **“No seeds provided”** – pass `URL=...` to `make crawl` or populate `crawler/seeds.txt`.
- **Empty results** – confirm `data/crawl/normalized.jsonl` exists, then run `make reindex`.
- **Playwright prompts** – `make setup` installs Chromium automatically; re-run if browsers are missing.
- **Non-3.11 Python** – run `./scripts/ensure_py311.sh python3` before `make setup`.

## Docker (optional)

The included Dockerfile + Compose definition build on Python 3.11. Update the bind mounts or environment variables if you want to persist data outside the container.
