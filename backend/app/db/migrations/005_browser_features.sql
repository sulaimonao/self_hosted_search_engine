PRAGMA foreign_keys=ON;

ALTER TABLE crawl_jobs ADD COLUMN priority INTEGER DEFAULT 0;
ALTER TABLE crawl_jobs ADD COLUMN reason TEXT;
ALTER TABLE crawl_jobs ADD COLUMN enqueued_at DATETIME DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE crawl_jobs ADD COLUMN finished_at DATETIME;

CREATE TABLE IF NOT EXISTS tabs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shadow_mode TEXT CHECK(shadow_mode IN ('off','visited_only','visited_outbound'))
);

CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tab_id TEXT,
    url TEXT NOT NULL,
    title TEXT,
    visited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    referrer TEXT,
    status_code INTEGER,
    content_type TEXT,
    shadow_enqueued BOOLEAN DEFAULT 0,
    FOREIGN KEY(tab_id) REFERENCES tabs(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_history_tab_time ON history(tab_id, visited_at DESC);
CREATE INDEX IF NOT EXISTS idx_history_url ON history(url);

CREATE TABLE IF NOT EXISTS bookmark_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    parent_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(parent_id) REFERENCES bookmark_folders(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bookmark_folders_parent ON bookmark_folders(parent_id);

CREATE TABLE IF NOT EXISTS bookmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_id INTEGER,
    url TEXT NOT NULL,
    title TEXT,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(folder_id) REFERENCES bookmark_folders(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_bookmarks_folder ON bookmarks(folder_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_url ON bookmarks(url);

CREATE TABLE IF NOT EXISTS source_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    label TEXT NOT NULL
);

INSERT OR IGNORE INTO source_categories(key, label) VALUES
    ('news', 'News & Current Affairs'),
    ('music', 'Music & Culture'),
    ('entertainment', 'Entertainment & Media'),
    ('art', 'Art & Design'),
    ('tech', 'Technology & Science');

CREATE TABLE IF NOT EXISTS seed_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_key TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT,
    added_by TEXT CHECK(added_by IN ('user','llm')) DEFAULT 'user',
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category_key, url),
    FOREIGN KEY(category_key) REFERENCES source_categories(key) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_seed_sources_category ON seed_sources(category_key, enabled);

CREATE TABLE IF NOT EXISTS shadow_settings (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    enabled BOOLEAN NOT NULL DEFAULT 0,
    mode TEXT CHECK(mode IN ('off','visited_only','visited_outbound')) NOT NULL DEFAULT 'off',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE,
    site TEXT,
    title TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen TIMESTAMP,
    topics TEXT,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_pages_site ON pages(site);
CREATE INDEX IF NOT EXISTS idx_pages_last_seen ON pages(last_seen DESC);

CREATE TABLE IF NOT EXISTS link_edges (
    src_url TEXT,
    dst_url TEXT,
    relation TEXT DEFAULT 'link',
    PRIMARY KEY (src_url, dst_url)
);
CREATE INDEX IF NOT EXISTS idx_link_edges_src ON link_edges(src_url);
CREATE INDEX IF NOT EXISTS idx_link_edges_dst ON link_edges(dst_url);
