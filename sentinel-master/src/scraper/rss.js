'use strict';

const path     = require('path');
const fs       = require('fs');
const crypto   = require('crypto');
const Parser   = require('rss-parser');
const Database = require('better-sqlite3');

const DB_PATH = path.resolve(__dirname, '../../data/sentinel.sqlite');
const REGISTRY_PATH = path.resolve(__dirname, '../../sources/registry.json');

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isoWeekNumber(dateInput) {
  const d = new Date(dateInput);
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNum   = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return `${d.getUTCFullYear()}-W${String(weekNum).padStart(2, '0')}`;
}

function articleId(url, publishedAt) {
  return crypto.createHash('sha256').update(url + (publishedAt || '')).digest('hex');
}

function loadRegistry() {
  return JSON.parse(fs.readFileSync(REGISTRY_PATH, 'utf8'));
}

function saveRegistry(registry) {
  fs.writeFileSync(REGISTRY_PATH, JSON.stringify(registry, null, 2), 'utf8');
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

// ─── Core ─────────────────────────────────────────────────────────────────────

async function runRssScraper(tierFilter) {
  const registry = loadRegistry();
  let sources = registry.sources.filter(s => s.method === 'rss' && s.active === true);
  if (tierFilter) {
    sources = sources.filter(s => s.tier === tierFilter);
    console.log(`[RSS] Filtering to tier ${tierFilter} — ${sources.length} sources`);
  }

  if (sources.length === 0) {
    console.log('[RSS] No active RSS sources found in registry.');
    return;
  }

  const db     = new Database(DB_PATH);
  const stmts  = prepareStatements(db);
  const parser = new Parser({
    timeout: 30000,
    headers: { 'User-Agent': 'Sentinel/1.0 (+https://github.com/yourhandle/sentinel)' },
    customFields: {
      item: [['content:encoded', 'contentEncoded']],
    },
  });

  let totalNew = 0;

  for (const source of sources) {
    console.log(`[RSS] ${source.id} — fetching...`);
    const runAt   = new Date().toISOString();
    const startMs = Date.now();
    let articlesFound = 0;
    let articlesNew   = 0;
    let errorMsg      = null;

    try {
      let feed;
      try {
        feed = await parser.parseURL(source.url);
      } catch (firstErr) {
        if (firstErr.message && (firstErr.message.includes('timeout') || firstErr.code === 'ECONNABORTED')) {
          console.warn(`[RSS] ${source.id} — timeout, retrying in 5s...`);
          await new Promise(r => setTimeout(r, 5000));
          feed = await parser.parseURL(source.url);
        } else {
          throw firstErr;
        }
      }

      articlesFound = (feed.items || []).length;

      const insertBatch = db.transaction((items) => {
        for (const item of items) {
          const url = (item.link || item.guid || '').trim();
          if (!url) continue;
          if (stmts.urlExists.get(url)) continue;

          const publishedAt = item.isoDate || item.pubDate || null;
          const ingestedAt  = new Date().toISOString();
          const body        = item.contentEncoded || item.content || item.contentSnippet || null;
          const summary     = item.contentSnippet
            ? item.contentSnippet.slice(0, 300)
            : (body ? body.slice(0, 300) : null);

          const article = {
            id:              articleId(url, publishedAt),
            source_id:       source.id,
            source_name:     source.name,
            tier:            source.tier,
            category:        source.category,
            url,
            title:           item.title || null,
            body,
            summary,
            published_at:    publishedAt,
            ingested_at:     ingestedAt,
            language_orig:   source.language,
            body_translated: null,
            relevance_score: null,
            relevance_note:  null,
            event_type:      null,
            entities:        null,
            passed_scoring:  0,
            week_number:     isoWeekNumber(ingestedAt),
            sector:          source.sector || 'general',
            sector_scores:   '{}',
          };

          const result = stmts.insertArticle.run(article);
          if (result.changes > 0) {
            stmts.insertSeenUrl.run(url, source.id, ingestedAt);
            articlesNew++;
          }
        }
      });

      insertBatch(feed.items || []);
      const durationMs = Date.now() - startMs;

      stmts.insertScrapeLog.run({
        source_id: source.id, run_at: runAt,
        articles_found: articlesFound, articles_new: articlesNew,
        error: null, duration_ms: durationMs,
      });

      const idx = registry.sources.findIndex(s => s.id === source.id);
      if (idx !== -1) {
        registry.sources[idx].last_checked     = runAt;
        registry.sources[idx].last_success     = runAt;
        registry.sources[idx].last_new_articles = articlesNew;
      }

      totalNew += articlesNew;
      console.log(`[RSS] ${source.id} — ${articlesNew} new / ${articlesFound} total`);

    } catch (err) {
      errorMsg = err.message;
      const durationMs = Date.now() - startMs;

      stmts.insertScrapeLog.run({
        source_id: source.id, run_at: runAt,
        articles_found: 0, articles_new: 0,
        error: errorMsg, duration_ms: durationMs,
      });

      const idx = registry.sources.findIndex(s => s.id === source.id);
      if (idx !== -1) {
        registry.sources[idx].last_checked = runAt;
        registry.sources[idx].error_count  = (registry.sources[idx].error_count || 0) + 1;
      }

      console.error(`[RSS] ${source.id} — ERROR: ${errorMsg}`);
    }
  }

  db.close();
  saveRegistry(registry);
  console.log(`[RSS] Run complete. ${sources.length} sources. ${totalNew} total new articles.`);
  return { sources: sources.length, totalNew };
}

if (require.main === module) {
  const tierArg = parseInt(process.argv[2]) || null;
  runRssScraper(tierArg).catch(err => {
    console.error('[RSS] Fatal error:', err.message);
    process.exit(1);
  });
}

module.exports = { runRssScraper };
