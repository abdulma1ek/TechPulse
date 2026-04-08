'use strict';

const path    = require('path');
const axios   = require('axios');
const Database = require('better-sqlite3');
const OpenAI  = require('openai');

const DB_PATH   = path.resolve(__dirname, '../../data/sentinel.sqlite');
const MODEL    = process.env.LLM_MODEL    || 'gpt-4o-mini';
const BASE_URL = process.env.LLM_BASE_URL || 'https://api.openai.com/v1';
const API_KEY  = process.env.LLM_API_KEY;

const openai = new OpenAI({ apiKey: API_KEY, baseURL: BASE_URL });

const SCORE_THRESHOLD     = 5;
const API_DELAY_MS        = 500;
const SHARED_SECTOR_DELAY = 300;
const ARTICLES_PER_RUN    = 50;

const ACTIVE_SECTORS = ['oil', 'banking'];

// ─── Sector scoring prompts — customize these per deployment ──────────────────

const SECTOR_PROMPTS = {
  oil: `You are an intelligence analyst scoring news articles.

TASK: Score this article 0-10 for relevance to the energy sector.
10 = directly about energy production, regulation, or major market events
7-9 = strongly affects energy sector (policy, macro, geopolitics)
4-6 = moderate indirect relevance
1-3 = weak connection
0 = not relevant

Respond ONLY with valid JSON:
{
  "relevance_score": <number 0-10>,
  "relevance_note": "<one sentence>",
  "event_type": "<production | contract | disruption | political | pricing | sanctions | macro-report | other>",
  "entities": ["<entity 1>", "<entity 2>"]
}`,

  banking: `You are an intelligence analyst scoring news articles.

TASK: Score this article 0-10 for relevance to the financial / banking sector.
10 = directly about central bank decisions, regulation, or major financial events
7-9 = strongly affects banking sector (macro, policy, sovereign events)
4-6 = moderate indirect relevance
1-3 = weak connection
0 = not relevant

Respond ONLY with valid JSON:
{
  "relevance_score": <number 0-10>,
  "relevance_note": "<one sentence>",
  "event_type": "<fx-policy | monetary-policy | banking-regulation | liquidity | digital-payments | sovereign-wealth | sanctions | macro-report | other>",
  "entities": ["<entity 1>", "<entity 2>"]
}`,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

const sanitize = (str) => {
  if (!str) return '';
  return str.replace(/[\u0000-\u001F\u007F]/g, ' ').replace(/\\/g, '\\\\').replace(/"/g, '\\"').slice(0, 500);
};

function safeParseJSON(str) {
  try { return JSON.parse(str); } catch {
    const scoreMatch = str.match(/"relevance_score"\s*:\s*(\d+(?:\.\d+)?)/);
    const noteMatch  = str.match(/"relevance_note"\s*:\s*"([^"]{0,200})"/);
    const eventMatch = str.match(/"event_type"\s*:\s*"([^"]+)"/);
    if (scoreMatch) {
      return {
        relevance_score: parseFloat(scoreMatch[1]),
        relevance_note: noteMatch ? noteMatch[1] : 'extracted from partial',
        event_type: eventMatch ? eventMatch[1] : 'other',
        entities: [],
      };
    }
    throw new Error('Could not parse or recover JSON');
  }
}

function buildUserMessage(article) {
  const title = sanitize(article.title);
  const body  = sanitize(article.body_translated || article.body || article.summary || '');
  return `TITLE: ${title || '(no title)'}\nSOURCE: ${article.source_name}\nBODY: ${body}`;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── API call ────────────────────────────────────────────────────────────────

async function callLLM(systemPrompt, userMessage) {
  const resp = await openai.chat.completions.create({
    model: MODEL,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user',   content: userMessage },
    ],
    max_tokens: 1024,
    temperature: 0,
  });
  const raw = resp.choices[0]?.message?.content || '';
  const stripped = raw.replace(/<think>[\s\S]*?<\/think>/g, '').replace(/```json\s*/g, '').replace(/```\s*/g, '').trim();
  return safeParseJSON(stripped);
}

// ─── Prepared statements ─────────────────────────────────────────────────────

function prepareStatements(db) {
  return {
    getPending: db.prepare(`
      SELECT * FROM articles
      WHERE passed_scoring = 0
      ORDER BY ingested_at ASC
      LIMIT ${ARTICLES_PER_RUN}
    `),
    passArticle: db.prepare(`
      UPDATE articles SET
        relevance_score = @relevance_score,
        relevance_note  = @relevance_note,
        event_type      = @event_type,
        entities        = @entities,
        sector          = @sector,
        sector_scores   = @sector_scores,
        passed_scoring  = 1
      WHERE id = @id
    `),
    dropArticle: db.prepare('DELETE FROM articles WHERE id = ?'),
    insertDropped: db.prepare(`
      INSERT INTO dropped_articles (source_id, url, title, relevance_score, relevance_note, dropped_at, reason, sector)
      VALUES (@source_id, @url, @title, @relevance_score, @relevance_note, @dropped_at, @reason, @sector)
    `),
  };
}

// ─── Scoring logic ────────────────────────────────────────────────────────────

async function scoreShared(article, stmts, apiCallMadeRef) {
  const titlePreview = (article.title || '').slice(0, 60);
  const userMessage  = buildUserMessage(article);
  const scores       = {};
  let bestScore = 0, bestResult = null;

  try {
    for (const sector of ACTIVE_SECTORS) {
      if (apiCallMadeRef.value) await sleep(SHARED_SECTOR_DELAY);
      const result = await callLLM(SECTOR_PROMPTS[sector], userMessage);
      apiCallMadeRef.value = true;
      scores[sector] = result.relevance_score;
      if (result.relevance_score > bestScore) { bestScore = result.relevance_score; bestResult = result; }
    }

    if (bestScore >= SCORE_THRESHOLD) {
      stmts.passArticle.run({
        id: article.id, relevance_score: bestScore,
        relevance_note: bestResult?.relevance_note || null,
        event_type: bestResult?.event_type || 'other',
        entities: JSON.stringify(Array.isArray(bestResult?.entities) ? bestResult.entities : []),
        sector: 'shared', sector_scores: JSON.stringify(scores),
      });
      return { passed: true, error: false };
    } else {
      stmts.insertDropped.run({
        source_id: article.source_id, url: article.url,
        title: article.title || null, relevance_score: bestScore,
        relevance_note: bestResult?.relevance_note || null,
        dropped_at: new Date().toISOString(), reason: 'below_threshold', sector: 'shared',
      });
      stmts.dropArticle.run(article.id);
      return { passed: false, error: false };
    }
  } catch (err) {
    console.error(`[SCORER] shared — ERROR: ${err.message}`);
    return { passed: false, error: true };
  }
}

async function scoreWithApi(article, stmts) {
  const titlePreview = (article.title || '').slice(0, 60);
  const sector = article.sector || 'oil';
  const prompt = SECTOR_PROMPTS[sector] || SECTOR_PROMPTS.oil;
  const userMessage = buildUserMessage(article);

  try {
    const result = await callLLM(prompt, userMessage);
    const score  = typeof result.relevance_score === 'number' ? result.relevance_score : null;

    if (score === null) throw new Error('Missing relevance_score');

    if (score >= SCORE_THRESHOLD) {
      stmts.passArticle.run({
        id: article.id, relevance_score: score,
        relevance_note: result.relevance_note || null,
        event_type: result.event_type || 'other',
        entities: JSON.stringify(Array.isArray(result.entities) ? result.entities : []),
        sector, sector_scores: JSON.stringify({ [sector]: score }),
      });
      return { passed: true, error: false };
    } else {
      stmts.insertDropped.run({
        source_id: article.source_id, url: article.url,
        title: article.title || null, relevance_score: score,
        relevance_note: result.relevance_note || null,
        dropped_at: new Date().toISOString(), reason: 'below_threshold', sector,
      });
      stmts.dropArticle.run(article.id);
      return { passed: false, error: false };
    }
  } catch (err) {
    console.error(`[SCORER] ${article.source_id} — ERROR: ${err.message}`);
    return { passed: false, error: true };
  }
}

// ─── Core ─────────────────────────────────────────────────────────────────────

async function runScorer() {
  if (!API_KEY) {
    console.error('[SCORER] LLM_API_KEY not set — cannot run. Add it to .env');
    process.exit(1);
  }

  const db    = new Database(DB_PATH);
  const stmts = prepareStatements(db);
  const articles = stmts.getPending.all();

  console.log(`[SCORER] Starting — ${articles.length} articles pending`);

  if (articles.length === 0) {
    db.close();
    return { scored: 0, passed: 0, dropped: 0, errors: 0 };
  }

  let passed = 0, dropped = 0, errors = 0;
  const apiCallMadeRef = { value: false };

  for (const article of articles) {
    let result;
    if (article.sector === 'shared') {
      result = await scoreShared(article, stmts, apiCallMadeRef);
    } else {
      if (apiCallMadeRef.value) await sleep(API_DELAY_MS);
      result = await scoreWithApi(article, stmts);
      apiCallMadeRef.value = true;
    }
    if (result.error) errors++;
    else if (result.passed) passed++;
    else dropped++;
  }

  db.close();
  console.log(`[SCORER] Done — ${passed} passed, ${dropped} dropped, ${errors} errors`);
  return { scored: articles.length - errors, passed, dropped, errors };
}

if (require.main === module) {
  runScorer().catch(err => {
    console.error('[SCORER] Fatal error:', err.message);
    process.exit(1);
  });
}

module.exports = { runScorer };
