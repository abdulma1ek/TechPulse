'use strict';

const path     = require('path');
const fs       = require('fs');
const crypto   = require('crypto');
const axios    = require('axios');
const pdfParse = require('pdf-parse');
const Database = require('better-sqlite3');

const DB_PATH       = path.resolve(__dirname, '../../data/sentinel.sqlite');
const REGISTRY_PATH = path.resolve(__dirname, '../../sources/registry.json');

function isoWeekNumber(dateInput) {
  const d = new Date(dateInput);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNum   = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

function articleId(url) {
  return crypto.createHash('sha256').update(url).digest('hex');
}

function loadRegistry() {
  return JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
}

function prepareStatements(db) {
  return {
    urlExists: db.prepare('SELECT 1 FROM seen_urls WHERE url = ?'),
    insertSeenUrl: db.prepare(
      'INSERT OR IGNORE INTO seen_urls (url, source_id, first_seen) VALUES (?, ?, ?)'
    ),
    insertArticle: db.prepare(`
      INSERT OR IGNORE INTO articles (
        id, source_id, source_name, tier, category,
        url, title, body, summary,
        published_at, ingested_at, language_orig,
        body_translated, relevance_score, relevance_note,
        event_type, entities, passed_scoring, week_number,
        sector, sector_scores
      ) VALUES (
        @id, @source_id, @source_name, @tier, @category,
        @url, @title, @body, @summary,
        @published_at, @ingested_at, @language_orig,
        @body_translated, @relevance_score, @relevance_note,
        @event_type, @entities, @passed_scoring, @week_number,
        @sector, @sector_scores
      )
    `),
    insertScrapeLog: db.prepare(`
      INSERT INTO scrape_log (source_id, run_at, articles_found, articles_new, error, duration_ms)
      VALUES (@source_id, @run_at, @articles_found, @articles_new, @error, @duration_ms)
    `),
  };
}

async function runPdfScraper() {
  const registry = loadRegistry();
  const sources  = registry.sources.filter(s => s.method === 'pdf' && s.active === true);

  if (sources.length === 0) {
    console.log('[PDF] No active PDF sources found in registry.');
    return;
  }

  const db    = new Database(DB_PATH);
  const stmts = prepareStatements(db);
  let totalNew = 0;

  for (const source of sources) {
    console.log(`[PDF] ${source.id} — fetching...`);
    const runAt   = new Date().toISOString();
    const startMs = Date.now();

    try {
      const resp = await axios.get(source.url, {
        timeout: 60000,
        responseType: 'arraybuffer',
        headers: { 'User-Agent': 'Sentinel/1.0 (+https://github.com/yourhandle/sentinel)' },
      });

      const pdfData = await pdfParse(resp.data);
      const text    = pdfData.text.slice(0, 5000);
      const title   = source.name + ' — ' + new Date().toISOString().slice(0, 10);
      const id      = articleId(source.url);
      const ingestedAt = runAt;

      if (!stmts.urlExists.get(source.url)) {
        stmts.insertArticle.run({
          id, source_id: source.id, source_name: source.name,
          tier: source.tier, category: source.category,
          url: source.url, title, body: text, summary: text.slice(0, 300),
          published_at: null, ingested_at: ingestedAt,
          language_orig: source.language,
          body_translated: null, relevance_score: null,
          relevance_note: null, event_type: null,
          entities: null, passed_scoring: 0,
          week_number: isoWeekNumber(ingestedAt),
          sector: source.sector || 'general',
          sector_scores: '{}',
        });
        stmts.insertSeenUrl.run(source.url, source.id, ingestedAt);
        totalNew++;

        stmts.insertScrapeLog.run({
          source_id: source.id, run_at: runAt,
          articles_found: 1, articles_new: 1,
          error: null, duration_ms: Date.now() - startMs,
        });
      } else {
        stmts.insertScrapeLog.run({
          source_id: source.id, run_at: runAt,
          articles_found: 1, articles_new: 0,
          error: null, duration_ms: Date.now() - startMs,
        });
      }

      console.log(`[PDF] ${source.id} — done`);

    } catch (err) {
      console.error(`[PDF] ${source.id} — ERROR: ${err.message}`);
      stmts.insertScrapeLog.run({
        source_id: source.id, run_at: runAt,
        articles_found: 0, articles_new: 0,
        error: err.message, duration_ms: Date.now() - startMs,
      });
    }
  }

  db.close();
  console.log(`[PDF] Run complete. ${totalNew} new articles.`);
  return { totalNew };
}

if (require.main === module) {
  runPdfScraper().catch(err => {
    console.error('[PDF] Fatal error:', err.message);
    process.exit(1);
  });
}

module.exports = { runPdfScraper };
