# Self-Hosted Search Engine

A privacy-first search stack that you can run entirely on your own machine. It combines a polite Scrapy crawler, a resumable SQLite-backed frontier, a Whoosh BM25 index, and a responsive Flask UI. No third-party APIs, telemetry, or hosted services are required.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install --with-deps chromium  # optional if you plan to render JS

# or simply
make setup
```

1. **Seed & crawl**
   ```bash
   make crawl
   ```
   This loads seed URLs/domains/sitemaps from `config.yaml`, keeps `data/frontier.sqlite` in sync, and launches the Scrapy frontier spider with conservative defaults (robots-aware, per-domain throttling, JS fallback only when necessary).

2. **Build or update the index**
   ```bash
   make index      # incremental
   make reindex    # full rebuild
   ```

3. **Run the UI**
   ```bash
   make serve
   ```
   Visit [http://127.0.0.1:5000](http://127.0.0.1:5000) for a clean search experience with highlighting, pagination, domain filters (`site:`), and an `in:title` toggle.

4. **Search from the CLI**
   ```bash
   python cli_search.py --site example.com "test query"
   ```

5. **Validate**
   ```bash
   make test
   ```

## Configuration (`config.yaml`)

All components pull from a single YAML file at the project root. Key sections:

```yaml
crawler:
  user_agent: "SelfHostedSearchBot/0.1 (+local)"
  obey_robots: true
  download_delay_sec: 0.8
  concurrent_requests: 8
  concurrent_per_domain: 4
  depth_limit: 2
  per_domain_page_cap: 5
  use_js_fallback: true
  js_fallback_threshold_chars: 200
  frontier_db: "data/frontier.sqlite"
  robots_cache_dir: "data/robots_cache"
  max_pages_total: 50000

seeds:
  urls_file: "seeds/seeds.txt"
  domains_file: "seeds/domains.txt"
  sitemaps_file: "seeds/sitemaps.txt"

index:
  dir: "index"
  analyzer: "stemming"
  field_boosts:
    title: 2.0
    content: 1.0
  incremental: true

ui:
  host: "127.0.0.1"
  port: 5000
  page_len: 10
```

Override any entry by exporting an uppercase environment variable (`.` replaced with `_`). Example: `CRAWLER_DOWNLOAD_DELAY_SEC=1.5` or `INDEX_DIR=/mnt/index`. Copy `.env.example` to `.env` for local overrides.

## Crawling pipeline

* **Frontier** – URLs are persisted in `data/frontier.sqlite` with status, depth, and JS rendering flags. The spider resumes unfinished work and enforces per-domain caps.
* **Seeds** – Populate `seeds/seeds.txt`, `seeds/domains.txt`, or `seeds/sitemaps.txt`. A helper (`scripts/frontier_tool.py`) can inspect, export, clear, or reseed the frontier.
* **Sitemaps** – Sitemap URLs are fetched, expanded recursively, and enqueued (respecting per-domain limits) before crawling.
* **Politeness** – Robots.txt obeyed by default, cached in `data/robots_cache`. User-agent and crawl delay configurable.
* **JS fallback** – Lightweight HTTP fetch first; if rendered text is below the configured threshold the page is re-queued once with Playwright rendering.
* **Deduplication** – Normalized URLs plus SHA-256 hashes of extracted text prevent duplicate storage. Unique documents append to `data/pages.jsonl`, and hashes are persisted in `data/pages_meta.sqlite`.
* **Logging & stats** – Structured logs live at `data/crawler.log`. End-of-run stats (pages fetched, failures, per-domain counts, average latency) are written to `data/crawl_stats.json` and surfaced via `make stats`.

## Indexing

`index_build.py` reads `data/pages.jsonl` and updates a Whoosh index in `index/`:

* Incremental by default (`index.incremental=true`), skipping documents whose content hash is unchanged (`data/index_meta.sqlite`).
* Analyzer can be switched between stemming and simple tokenization.
* Field boosts align with config for BM25 scoring (title vs. content weights).
* `python index_build.py full` nukes and rebuilds the index; `python index_build.py update` (default) only adds/updates documents.

## Search UI

`app/main.py` exposes a Flask application with:

* Search across titles & content with highlighting.
* `site:` filter (via domain keyword) and optional `in:title` bias.
* Pagination length sourced from config.
* `/healthz` endpoint for monitoring.

Use `scripts/manage.py serve` (or `make serve`) to launch with config-driven host/port.

## CLI & management tools

* `scripts/manage.py crawl|sitemapseed|index|serve|stats`
* `scripts/frontier_tool.py stats|export|clear|seed`
* `cli_search.py` for quick terminal searches.

## Phonebook vs. depth mode

* **Phonebook mode** – Keep `depth_limit` low (1–2) and `per_domain_page_cap` small to capture one high-value page per domain quickly.
* **Depth mode** – Increase `depth_limit` and domain cap for deeper site exploration. Adjust `concurrent_requests` and `download_delay_sec` to balance speed with politeness.

## Operational notes

* Prefer SSD/NVMe for both `data/` and `index/` directories; latency-sensitive operations benefit greatly.
* Large crawls (tens of thousands of pages) may require >8 GB RAM when rendering JS. Disable fallback if headless Chromium is unnecessary.
* Consider running crawls during off-peak hours to minimize load on target hosts.

## Troubleshooting

* **Empty results:** ensure crawl completed (`make stats`), rebuild the index, or enable JS fallback for SPA-heavy sites.
* **Slow queries:** lower `ui.page_len`, increase title boost, or switch to the simple analyzer.
* **Index corruption:** run `make reindex` to rebuild from `data/pages.jsonl`.
* **Crawler stops early:** inspect `data/crawler.log` and `scripts/frontier_tool.py stats` for domain caps or robots exclusions.

## Docker & Compose

```bash
docker compose up --build
```

* Multi-stage Dockerfile based on Python slim; pass `--build-arg USE_JS_FALLBACK=false` to avoid Playwright system dependencies.
* `docker-compose.yml` binds `./data` and `./index` into the container and health-checks `/healthz`.

## Continuous Integration

GitHub Actions (`.github/workflows/ci.yml`) runs `pytest -q` on Python 3.10 and 3.11 for every push/PR.

## Next steps

Ideas for future enhancements: vector search or hybrid reranking, SimHash/MinHash for near-duplicate detection, optional Meilisearch backend, richer UI facets, and scheduled crawl orchestration.
