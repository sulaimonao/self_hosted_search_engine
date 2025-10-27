CREATE TABLE IF NOT EXISTS domain_profiles (
  host TEXT PRIMARY KEY,
  pages_cached INTEGER DEFAULT 0,
  robots_txt TEXT,
  robots_allows INTEGER DEFAULT 0,
  robots_disallows INTEGER DEFAULT 0,
  requires_account INTEGER DEFAULT 0,
  clearance TEXT DEFAULT 'public',
  sitemaps TEXT,
  subdomains TEXT,
  last_scanned REAL
);
