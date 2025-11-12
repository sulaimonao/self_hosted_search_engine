CREATE TABLE IF NOT EXISTS domain_graph_domains (
  id INTEGER PRIMARY KEY,
  host TEXT NOT NULL UNIQUE,
  first_seen REAL,
  last_seen REAL,
  pages_count INTEGER NOT NULL DEFAULT 0,
  edges_count INTEGER NOT NULL DEFAULT 0,
  queue_size INTEGER NOT NULL DEFAULT 0,
  last_crawled REAL,
  crawl_cap INTEGER DEFAULT 200,
  crawl_rps REAL DEFAULT 1.0
);

CREATE INDEX IF NOT EXISTS idx_domain_graph_domains_last_seen ON domain_graph_domains(last_seen DESC);

CREATE TABLE IF NOT EXISTS domain_graph_pages (
  id INTEGER PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domain_graph_domains(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  title TEXT,
  content_hash TEXT,
  tokens INTEGER,
  word_count INTEGER,
  text_preview TEXT,
  headings TEXT,
  meta TEXT,
  first_seen REAL,
  last_seen REAL,
  status TEXT,
  is_sample INTEGER NOT NULL DEFAULT 0,
  UNIQUE(domain_id, url_hash)
);

CREATE INDEX IF NOT EXISTS idx_domain_graph_pages_domain_seen ON domain_graph_pages(domain_id, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_domain_graph_pages_url_hash ON domain_graph_pages(url_hash);

CREATE TABLE IF NOT EXISTS domain_graph_edges (
  id INTEGER PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domain_graph_domains(id) ON DELETE CASCADE,
  src_page_id INTEGER REFERENCES domain_graph_pages(id) ON DELETE CASCADE,
  dst_url TEXT NOT NULL,
  dst_host TEXT,
  rel TEXT,
  weight REAL DEFAULT 1.0,
  first_seen REAL,
  last_seen REAL
);

CREATE INDEX IF NOT EXISTS idx_domain_graph_edges_domain ON domain_graph_edges(domain_id, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_domain_graph_edges_src ON domain_graph_edges(src_page_id);

CREATE TABLE IF NOT EXISTS domain_graph_visits (
  id INTEGER PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domain_graph_domains(id) ON DELETE CASCADE,
  page_id INTEGER REFERENCES domain_graph_pages(id) ON DELETE SET NULL,
  seen_at REAL NOT NULL,
  bytes INTEGER,
  dur_ms INTEGER,
  source TEXT,
  status TEXT
);

CREATE INDEX IF NOT EXISTS idx_domain_graph_visits_domain ON domain_graph_visits(domain_id, seen_at DESC);

CREATE TABLE IF NOT EXISTS domain_graph_stats (
  id INTEGER PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domain_graph_domains(id) ON DELETE CASCADE,
  day TEXT NOT NULL,
  pages_delta INTEGER DEFAULT 0,
  edges_delta INTEGER DEFAULT 0,
  bytes_delta INTEGER DEFAULT 0,
  UNIQUE(domain_id, day)
);

CREATE TABLE IF NOT EXISTS domain_graph_queue (
  id INTEGER PRIMARY KEY,
  domain_id INTEGER NOT NULL REFERENCES domain_graph_domains(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  enqueued_at REAL NOT NULL,
  priority INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  last_attempt REAL,
  status TEXT,
  error TEXT,
  source TEXT,
  UNIQUE(domain_id, url_hash)
);

CREATE INDEX IF NOT EXISTS idx_domain_graph_queue_domain ON domain_graph_queue(domain_id, priority DESC, enqueued_at ASC);
