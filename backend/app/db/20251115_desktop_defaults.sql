-- Additional desktop and diagnostics defaults for existing installations.
CREATE TABLE IF NOT EXISTS app_config (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

INSERT OR IGNORE INTO app_config(k, v) VALUES
('DESKTOP_USER_AGENT',          '""'),
('AGENT_BROWSER_ENABLED',          'true'),
('AGENT_BROWSER_HEADLESS',          'false'),
('AGENT_BROWSER_DEFAULT_TIMEOUT_S',          '30'),
('AGENT_BROWSER_NAV_TIMEOUT_MS',          '20000'),
('DIAG_TIMEOUT',          '60'),
('DESKTOP_PREFLIGHT_HEALTH_ATTEMPTS',          '3');
