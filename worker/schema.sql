CREATE TABLE IF NOT EXISTS articles (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, effective_ms INTEGER NOT NULL,
 tags TEXT NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL, content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_time ON articles(effective_ms DESC,id DESC);
CREATE INDEX IF NOT EXISTS articles_source_time ON articles(source_id,effective_ms DESC,id DESC);
CREATE TABLE IF NOT EXISTS snapshots (key TEXT PRIMARY KEY,payload TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ai_daily (day TEXT PRIMARY KEY,calls INTEGER NOT NULL DEFAULT 0);
