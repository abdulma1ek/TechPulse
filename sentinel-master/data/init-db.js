'use strict';

const path     = require('path');
const fs       = require('fs');
const Database = require('better-sqlite3');

const DB_PATH = path.resolve(__dirname, 'sentinel.sqlite');

if (fs.existsSync(DB_PATH)) {
  console.log(`[DB] ${DB_PATH} already exists — no action taken.`);
  console.log('[DB] To reset: delete the file and run this script again.');
  process.exit(0);
}

const db = new Database(DB_PATH);

// WAL mode for better concurrent read performance
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

console.log('[DB] Creating schema...');

db.exec(`
  -- Master article table
  CREATE TABLE IF NOT EXISTS articles (
    id                 TEXT    PRIMARY KEY,
    source_id          TEXT    NOT NULL,
    source_name        TEXT,
    tier               INTEGER,
    category           TEXT,
    url                TEXT    NOT NULL,
    title              TEXT,
    body               TEXT,
    summary            TEXT,
    published_at       TEXT,
    ingested_at        TEXT    NOT NULL,
    language_orig      TEXT    DEFAULT 'en',
    body_translated    TEXT,
    relevance_score    REAL,
    relevance_note     TEXT,
    event_type         TEXT,
    entities           TEXT,
    passed_scoring     INTEGER DEFAULT 0,
    week_number        TEXT,
    sector             TEXT    DEFAULT 'general',
    sector_scores      TEXT
  );

  CREATE INDEX IF NOT EXISTS idx_articles_passed       ON articles(passed_scoring);
  CREATE INDEX IF NOT EXISTS idx_articles_ingested      ON articles(ingested_at);
  CREATE INDEX IF NOT EXISTS idx_articles_sector        ON articles(sector);
  CREATE INDEX IF NOT EXISTS idx_articles_week          ON articles(week_number);
  CREATE INDEX IF NOT EXISTS idx_articles_event        ON articles(event_type);

  -- Deduplication
  CREATE TABLE IF NOT EXISTS seen_urls (
    url         TEXT PRIMARY KEY,
    source_id   TEXT,
    first_seen  TEXT
  );

  -- Per-source scrape log
  CREATE TABLE IF NOT EXISTS scrape_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id        TEXT    NOT NULL,
    run_at           TEXT    NOT NULL,
    articles_found   INTEGER DEFAULT 0,
    articles_new     INTEGER DEFAULT 0,
    error            TEXT,
    duration_ms      INTEGER
  );

  CREATE INDEX IF NOT EXISTS idx_scrape_source ON scrape_log(source_id);
  CREATE INDEX IF NOT EXISTS idx_scrape_run    ON scrape_log(run_at);

  -- Dropped articles audit trail
  CREATE TABLE IF NOT EXISTS dropped_articles (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          TEXT,
    url                TEXT,
    title              TEXT,
    relevance_score    REAL,
    relevance_note     TEXT,
    dropped_at         TEXT,
    reason             TEXT,
    sector             TEXT
  );

  -- Source health tracking
  CREATE TABLE IF NOT EXISTS source_health (
    source_id   TEXT PRIMARY KEY,
    checked_at  TEXT,
    status      TEXT,
    error       TEXT,
    response_ms INTEGER
  );
`);

console.log('[DB] Schema created ✓');
console.log(`[DB] Database: ${DB_PATH}`);

db.close();
