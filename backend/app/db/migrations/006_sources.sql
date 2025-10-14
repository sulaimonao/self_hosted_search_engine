ALTER TABLE crawl_jobs ADD COLUMN parent_url TEXT;
ALTER TABLE crawl_jobs ADD COLUMN is_source INTEGER DEFAULT 0;

CREATE TABLE IF NOT EXISTS source_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_url TEXT NOT NULL,
  source_url TEXT NOT NULL,
  kind TEXT,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  enqueued INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_source_links_parent ON source_links(parent_url);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_links_unique ON source_links(parent_url, source_url);

CREATE TABLE IF NOT EXISTS missing_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_url TEXT NOT NULL,
  source_url TEXT NOT NULL,
  reason TEXT,
  http_status INTEGER,
  last_attempt TIMESTAMP,
  retries INTEGER DEFAULT 0,
  next_action TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_missing_sources_url ON missing_sources(source_url);
CREATE INDEX IF NOT EXISTS idx_missing_sources_parent ON missing_sources(parent_url);
CREATE UNIQUE INDEX IF NOT EXISTS idx_missing_sources_unique ON missing_sources(parent_url, source_url);

CREATE TABLE IF NOT EXISTS crawl_budgets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  max_pages INTEGER,
  max_minutes INTEGER,
  max_storage_mb INTEGER,
  pages_crawled INTEGER DEFAULT 0,
  bytes_stored INTEGER DEFAULT 0,
  UNIQUE(session_id)
);
