PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pending_documents (
  doc_id TEXT PRIMARY KEY,
  job_id TEXT,
  url TEXT,
  title TEXT,
  resolved_title TEXT,
  doc_hash TEXT,
  sim_signature INTEGER,
  metadata TEXT,
  created_at REAL DEFAULT (strftime('%s','now')),
  updated_at REAL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS pending_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL UNIQUE,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  metadata TEXT,
  created_at REAL DEFAULT (strftime('%s','now')),
  updated_at REAL DEFAULT (strftime('%s','now')),
  FOREIGN KEY(doc_id) REFERENCES pending_documents(doc_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_chunks_doc_seq ON pending_chunks(doc_id, chunk_index);

CREATE TABLE IF NOT EXISTS pending_vectors_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  next_attempt_at REAL DEFAULT (strftime('%s','now')),
  created_at REAL DEFAULT (strftime('%s','now')),
  updated_at REAL DEFAULT (strftime('%s','now')),
  FOREIGN KEY(doc_id) REFERENCES pending_documents(doc_id) ON DELETE CASCADE,
  UNIQUE(doc_id)
);
CREATE INDEX IF NOT EXISTS idx_pending_vectors_ready ON pending_vectors_queue(next_attempt_at ASC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_vectors_doc ON pending_vectors_queue(doc_id);
