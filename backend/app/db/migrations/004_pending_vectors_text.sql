BEGIN TRANSACTION;

-- Rebuild pending_documents to ensure large identifiers are stored as TEXT
-- and timestamps are stored as INTEGER seconds.
ALTER TABLE pending_documents RENAME TO pending_documents_old;

CREATE TABLE pending_documents (
  doc_id TEXT PRIMARY KEY,
  job_id TEXT,
  url TEXT,
  title TEXT,
  resolved_title TEXT,
  doc_hash TEXT,
  sim_signature TEXT,
  metadata TEXT,
  last_error TEXT,
  retry_count INTEGER DEFAULT 0,
  created_at INTEGER DEFAULT (strftime('%s','now')),
  updated_at INTEGER DEFAULT (strftime('%s','now'))
);

INSERT INTO pending_documents(
  doc_id,
  job_id,
  url,
  title,
  resolved_title,
  doc_hash,
  sim_signature,
  metadata,
  last_error,
  retry_count,
  created_at,
  updated_at
)
SELECT
  doc_id,
  CAST(job_id AS TEXT),
  url,
  title,
  resolved_title,
  CAST(doc_hash AS TEXT),
  CASE WHEN sim_signature IS NOT NULL THEN CAST(sim_signature AS TEXT) ELSE NULL END,
  metadata,
  last_error,
  COALESCE(retry_count, 0),
  COALESCE(CAST(created_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER)),
  COALESCE(CAST(updated_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER))
FROM pending_documents_old;

DROP TABLE pending_documents_old;

-- Rebuild pending_chunks with INTEGER timestamps to match pending_documents.
CREATE TABLE pending_chunks_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL,
  chunk_index INTEGER NOT NULL,
  text TEXT NOT NULL,
  metadata TEXT,
  created_at INTEGER DEFAULT (strftime('%s','now')),
  updated_at INTEGER DEFAULT (strftime('%s','now')),
  FOREIGN KEY(doc_id) REFERENCES pending_documents(doc_id) ON DELETE CASCADE
);

INSERT INTO pending_chunks_new(
  id,
  doc_id,
  chunk_index,
  text,
  metadata,
  created_at,
  updated_at
)
SELECT
  id,
  doc_id,
  chunk_index,
  text,
  metadata,
  COALESCE(CAST(created_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER)),
  COALESCE(CAST(updated_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER))
FROM pending_chunks;

DROP TABLE pending_chunks;
ALTER TABLE pending_chunks_new RENAME TO pending_chunks;

CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_chunks_doc_seq ON pending_chunks(doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS idx_pending_chunks_doc_id ON pending_chunks(doc_id);

-- Rebuild pending_vectors_queue with INTEGER timestamps.
ALTER TABLE pending_vectors_queue RENAME TO pending_vectors_queue_old;

CREATE TABLE pending_vectors_queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL,
  attempts INTEGER DEFAULT 0,
  next_attempt_at INTEGER DEFAULT (strftime('%s','now')),
  created_at INTEGER DEFAULT (strftime('%s','now')),
  updated_at INTEGER DEFAULT (strftime('%s','now')),
  FOREIGN KEY(doc_id) REFERENCES pending_documents(doc_id) ON DELETE CASCADE,
  UNIQUE(doc_id)
);

INSERT INTO pending_vectors_queue(
  id,
  doc_id,
  attempts,
  next_attempt_at,
  created_at,
  updated_at
)
SELECT
  id,
  doc_id,
  attempts,
  COALESCE(CAST(next_attempt_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER)),
  COALESCE(CAST(created_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER)),
  COALESCE(CAST(updated_at AS INTEGER), CAST(strftime('%s','now') AS INTEGER))
FROM pending_vectors_queue_old;

DROP TABLE pending_vectors_queue_old;

CREATE INDEX IF NOT EXISTS idx_pending_vectors_ready ON pending_vectors_queue(next_attempt_at ASC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_vectors_doc ON pending_vectors_queue(doc_id);

COMMIT;
