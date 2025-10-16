const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const SCHEMA = `
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  title TEXT,
  visit_time INTEGER NOT NULL,
  transition TEXT,
  referrer TEXT
);
CREATE INDEX IF NOT EXISTS idx_history_time ON history(visit_time DESC);
CREATE INDEX IF NOT EXISTS idx_history_url ON history(url);

CREATE TABLE IF NOT EXISTS visits (
  id INTEGER PRIMARY KEY,
  history_id INTEGER NOT NULL REFERENCES history(id) ON DELETE CASCADE,
  visit_time INTEGER NOT NULL,
  duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_visits_history ON visits(history_id);

CREATE TABLE IF NOT EXISTS downloads (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  filename TEXT,
  mime TEXT,
  bytes_total INTEGER,
  bytes_received INTEGER,
  path TEXT,
  state TEXT,
  started_at INTEGER,
  completed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_downloads_started ON downloads(started_at DESC);

CREATE TABLE IF NOT EXISTS permissions (
  origin TEXT NOT NULL,
  permission TEXT NOT NULL,
  setting TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(origin, permission)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
`;

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

class BrowserDataStore {
  constructor(database) {
    this.db = database;
    this.statements = {
      insertHistory: this.db.prepare(
        'INSERT INTO history(url, title, visit_time, transition, referrer) VALUES (?, ?, ?, ?, ?)',
      ),
      insertVisit: this.db.prepare(
        'INSERT INTO visits(history_id, visit_time, duration_ms) VALUES (?, ?, ?)',
      ),
      updateHistoryTitle: this.db.prepare('UPDATE history SET title=? WHERE id=?'),
      recentHistory: this.db.prepare(
        'SELECT id, url, title, visit_time AS visitTime, transition, referrer FROM history ORDER BY visit_time DESC LIMIT ?',
      ),
      insertDownload: this.db.prepare(
        'INSERT OR REPLACE INTO downloads(id, url, filename, mime, bytes_total, bytes_received, path, state, started_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
      ),
      recentDownloads: this.db.prepare(
        'SELECT id, url, filename, mime, bytes_total AS bytesTotal, bytes_received AS bytesReceived, path, state, started_at AS startedAt, completed_at AS completedAt FROM downloads ORDER BY started_at DESC LIMIT ?',
      ),
      getPermission: this.db.prepare(
        'SELECT setting FROM permissions WHERE origin=? AND permission=?',
      ),
      upsertPermission: this.db.prepare(
        'INSERT INTO permissions(origin, permission, setting, updated_at) VALUES (?, ?, ?, ?) ON CONFLICT(origin, permission) DO UPDATE SET setting=excluded.setting, updated_at=excluded.updated_at',
      ),
      listPermissionsForOrigin: this.db.prepare(
        'SELECT permission, setting, updated_at AS updatedAt FROM permissions WHERE origin=?',
      ),
      deletePermission: this.db.prepare('DELETE FROM permissions WHERE origin=? AND permission=?'),
      clearPermissionsForOrigin: this.db.prepare('DELETE FROM permissions WHERE origin=?'),
      setSetting: this.db.prepare(
        'INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
      ),
      getSetting: this.db.prepare('SELECT value FROM settings WHERE key=?'),
      allSettings: this.db.prepare('SELECT key, value FROM settings'),
    };
  }

  recordNavigation({ url, title, transition, referrer }) {
    const now = Date.now();
    const info = this.statements.insertHistory.run(url, title ?? null, now, transition ?? null, referrer ?? null);
    const historyId = Number(info.lastInsertRowid);
    this.statements.insertVisit.run(historyId, now, null);
    return { id: historyId, url, title: title ?? null, visitTime: now, transition: transition ?? null, referrer: referrer ?? null };
  }

  updateHistoryTitle(historyId, title) {
    this.statements.updateHistoryTitle.run(title ?? null, historyId);
  }

  getRecentHistory(limit = 100) {
    return this.statements.recentHistory.all(limit);
  }

  recordDownload(entry) {
    const now = entry.startedAt ?? Date.now();
    this.statements.insertDownload.run(
      entry.id,
      entry.url,
      entry.filename ?? null,
      entry.mime ?? null,
      entry.bytesTotal ?? null,
      entry.bytesReceived ?? 0,
      entry.path ?? null,
      entry.state ?? 'in_progress',
      now,
      entry.completedAt ?? null,
    );
  }

  updateDownloadProgress(id, { bytesReceived, bytesTotal, state, path, completedAt }) {
    const existing = this.getDownload(id) ?? {};
    this.recordDownload({
      id,
      url: existing.url ?? null,
      filename: existing.filename ?? null,
      mime: existing.mime ?? null,
      bytesTotal: bytesTotal ?? existing.bytesTotal ?? null,
      bytesReceived: bytesReceived ?? existing.bytesReceived ?? 0,
      path: path ?? existing.path ?? null,
      state: state ?? existing.state ?? 'in_progress',
      startedAt: existing.startedAt ?? Date.now(),
      completedAt: completedAt ?? existing.completedAt ?? null,
    });
  }

  getDownload(id) {
    return this.db.prepare(
      'SELECT id, url, filename, mime, bytes_total AS bytesTotal, bytes_received AS bytesReceived, path, state, started_at AS startedAt, completed_at AS completedAt FROM downloads WHERE id=?',
    ).get(id);
  }

  listDownloads(limit = 20) {
    return this.statements.recentDownloads.all(limit);
  }

  getPermission(origin, permission) {
    const row = this.statements.getPermission.get(origin, permission);
    return row ? row.setting : null;
  }

  savePermission(origin, permission, setting) {
    this.statements.upsertPermission.run(origin, permission, setting, Date.now());
  }

  listPermissions(origin) {
    return this.statements.listPermissionsForOrigin.all(origin);
  }

  clearPermission(origin, permission) {
    this.statements.deletePermission.run(origin, permission);
  }

  clearPermissionsForOrigin(origin) {
    this.statements.clearPermissionsForOrigin.run(origin);
  }

  setSetting(key, value) {
    const payload = value === undefined ? null : JSON.stringify(value);
    this.statements.setSetting.run(key, payload);
  }

  getSetting(key) {
    const row = this.statements.getSetting.get(key);
    if (!row || row.value == null) {
      return null;
    }
    try {
      return JSON.parse(row.value);
    } catch (error) {
      console.warn('Failed to parse setting', { key, error });
      return null;
    }
  }

  getAllSettings() {
    const rows = this.statements.allSettings.all();
    const result = {};
    for (const row of rows) {
      if (row.value == null) {
        result[row.key] = null;
        continue;
      }
      try {
        result[row.key] = JSON.parse(row.value);
      } catch (error) {
        console.warn('Failed to parse setting', { key: row.key, error });
        result[row.key] = null;
      }
    }
    return result;
  }
}

function initializeBrowserData(app) {
  const userData = app.getPath('userData');
  ensureDir(userData);
  const dbPath = path.join(userData, 'browser_state.sqlite3');
  const db = new Database(dbPath);
  db.pragma('foreign_keys = ON');
  db.exec(SCHEMA);
  return new BrowserDataStore(db);
}

module.exports = {
  initializeBrowserData,
  BrowserDataStore,
};
