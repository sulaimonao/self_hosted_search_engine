-- idempotent table for app-wide config
CREATE TABLE IF NOT EXISTS app_config (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- sensible defaults for zero-touch boot
INSERT OR IGNORE INTO app_config(k, v) VALUES
('models.primary',          '{"name": "gemma-3"}'),
('models.fallback',          '{"name": "gpt-oss"}'),
('models.embedder',          '{"name": "embeddinggemma"}'),
('features.shadow_mode',          'true'),
('features.agent_mode',          'true'),
('features.local_discovery',          'true'),
('features.browsing_fallbacks',          'true'),
('features.index_auto_rebuild',          'true'),
('features.auth_clearance_detectors',          'false'),
('chat.use_page_context_default',          'true'),
('browser.persist',          'true'),
('browser.allow_cookies',          'true'),
('sources.seed',          '{"news": [], "music": [], "tech": [], "art": [], "other": []}'),
('setup.completed',          'false');
