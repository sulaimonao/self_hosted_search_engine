BEGIN TRANSACTION;

-- Persist application settings (shadow toggle, etc.).
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at REAL DEFAULT (strftime('%s','now'))
);

INSERT OR IGNORE INTO app_settings(key, value)
VALUES ('shadow_enabled', 'false');

-- Structured job status/progress tracking for background tasks.
CREATE TABLE IF NOT EXISTS job_status (
  job_id TEXT PRIMARY KEY,
  url TEXT,
  phase TEXT,
  steps_total INTEGER DEFAULT 0,
  steps_completed INTEGER DEFAULT 0,
  retries INTEGER DEFAULT 0,
  eta_seconds REAL,
  message TEXT,
  started_at REAL DEFAULT (strftime('%s','now')),
  updated_at REAL DEFAULT (strftime('%s','now'))
);

-- Extend pending_documents with retry/error metadata for observability.
ALTER TABLE pending_documents ADD COLUMN last_error TEXT;
ALTER TABLE pending_documents ADD COLUMN retry_count INTEGER DEFAULT 0;

-- Rebuild pending_chunks to drop the erroneous UNIQUE(doc_id) constraint
-- while keeping existing data.
CREATE TABLE IF NOT EXISTS pending_chunks_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  metadata TEXT,
  created_at REAL DEFAULT (strftime('%s','now')),
  updated_at REAL DEFAULT (strftime('%s','now')),
  FOREIGN KEY(doc_id) REFERENCES pending_documents(doc_id) ON DELETE CASCADE
);

INSERT INTO pending_chunks_new(id, doc_id, chunk_index, text, metadata, created_at, updated_at)
SELECT id, doc_id, chunk_index, text, metadata, created_at, updated_at FROM pending_chunks;

DROP TABLE pending_chunks;
ALTER TABLE pending_chunks_new RENAME TO pending_chunks;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_chunks_doc_seq ON pending_chunks(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_pending_chunks_doc_id ON pending_chunks(doc_id);

-- Backfill retry_count from queue attempts where available.
UPDATE pending_documents
   SET retry_count = COALESCE((
     SELECT attempts FROM pending_vectors_queue WHERE pending_vectors_queue.doc_id = pending_documents.doc_id
   ), retry_count, 0);

COMMIT;
