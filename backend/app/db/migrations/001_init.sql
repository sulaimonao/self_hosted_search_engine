PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS crawl_jobs (
  id TEXT PRIMARY KEY,
  started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  status TEXT CHECK(status IN ('queued','running','success','error')) NOT NULL,
  seed TEXT,
  query TEXT,
  stats TEXT,
  error TEXT,
  normalized_path TEXT,
  preview_json TEXT
);

CREATE TABLE IF NOT EXISTS crawl_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  stage TEXT NOT NULL,
  payload TEXT,
  FOREIGN KEY(job_id) REFERENCES crawl_jobs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_crawl_events_job ON crawl_events(job_id, id DESC);

CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  canonical_url TEXT,
  site TEXT,
  title TEXT,
  description TEXT,
  authors TEXT,
  language TEXT,
  http_status INTEGER,
  mime_type TEXT,
  content_hash TEXT,
  fetched_at DATETIME,
  normalized_path TEXT,
  text_len INTEGER,
  tokens INTEGER,
  embeddings_ref TEXT,
  categories TEXT,
  labels TEXT,
  source TEXT,
  first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_seen DATETIME,
  job_id TEXT,
  verification TEXT,
  FOREIGN KEY(job_id) REFERENCES crawl_jobs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_url ON documents(url);
CREATE INDEX IF NOT EXISTS idx_documents_site ON documents(site);
CREATE INDEX IF NOT EXISTS idx_documents_last_seen ON documents(last_seen DESC);

CREATE TABLE IF NOT EXISTS page_visits (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  url TEXT NOT NULL,
  visited_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  referer TEXT,
  dur_ms INTEGER,
  source TEXT DEFAULT 'browser-mode'
);
CREATE INDEX IF NOT EXISTS idx_page_visits_url ON page_visits(url);

CREATE TABLE IF NOT EXISTS chat_threads (
  id TEXT PRIMARY KEY,
  title TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_activity DATETIME
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY,
  thread_id TEXT NOT NULL,
  role TEXT CHECK(role IN ('user','assistant','system')) NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  tokens INTEGER,
  FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_summaries (
  thread_id TEXT PRIMARY KEY,
  summary TEXT,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  embedding_ref TEXT,
  FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  scope TEXT CHECK(scope IN ('global','user','thread','doc')) NOT NULL,
  scope_ref TEXT,
  key TEXT,
  value TEXT,
  metadata TEXT,
  strength REAL DEFAULT 1.0,
  last_accessed DATETIME DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope, scope_ref);

CREATE TABLE IF NOT EXISTS memory_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  memory_id TEXT,
  action TEXT,
  detail TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
