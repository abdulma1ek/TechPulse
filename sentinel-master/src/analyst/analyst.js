'use strict';

const path     = require('path');
const fs       = require('fs');
const Database = require('better-sqlite3');
const OpenAI   = require('openai');

const DB_PATH   = path.resolve(__dirname, '../../data/sentinel.sqlite');
const MODEL    = process.env.LLM_MODEL    || 'gpt-4o-mini';
const BASE_URL = process.env.LLM_BASE_URL || 'https://api.openai.com/v1';
const API_KEY  = process.env.LLM_API_KEY;

const openai = new OpenAI({ apiKey: API_KEY, baseURL: BASE_URL });

const BRIEF_DATE = new Date().toISOString().slice(0, 10);
const SECTOR_LIST = ['oil', 'banking'];

// ─── Section templates per sector — customize per deployment ──────────────────

const SECTOR_TEMPLATES = {
  oil: {
    sections: [
      { id: 'prod',       title: 'Production & Operations' },
      { id: 'contracts',  title: 'Contracts & Deals' },
      { id: 'pricing',    title: 'Market & Pricing' },
      { id: 'regulatory', title: 'Political & Regulatory' },
      { id: 'macro',      title: 'Macro Context' },
    ],
    sectionPrompt:
      `For the {title} section, draw from articles tagged event_type: {event_types}.
       Focus on factual, specific claims. Use bullet points.`,
  },

  banking: {
    sections: [
      { id: 'fx',         title: 'FX & Monetary Policy' },
      { id: 'banking',    title: 'Banking Sector' },
      { id: 'liquidity',  title: 'Liquidity & Reserves' },
      { id: 'regulation', title: 'Regulatory' },
      { id: 'macro',      title: 'Macro Context' },
    ],
    sectionPrompt:
      `For the {title} section, draw from articles tagged with the relevant event types.
       Focus on factual, specific claims. Use bullet points.`,
  },
};

// ─── System prompt ────────────────────────────────────────────────────────────

function buildBriefingSystemPrompt() {
  const sectorDescs = SECTOR_LIST.map(s => {
    const tpl = SECTOR_TEMPLATES[s];
    return `${s}: sections [${tpl.sections.map(ss => ss.id).join(', ')}]`;
  }).join('\n');

  return `You are an intelligence analyst drafting a daily sector briefing.

OUTPUT FORMAT:
- Date header, then Executive Summary (3-5 sentence overview)
- Sections as defined per sector
- Bullet points, specific facts and numbers
- Watch list at the end (top 3 items to monitor)
- Tone: professional, factual, no opinion

SECTORS COVERED: ${sectorDescs}

Section authorships:
${SECTOR_LIST.map(s =>
  `${s}: ${SECTOR_TEMPLATES[s].sectionPrompt}`
).join('\n\n')}

Rules:
- Group related content into the appropriate section
- If no articles exist for a section, write "No significant developments today."
- Never invent facts — use only information from the provided articles
- Cite sources implicitly (e.g., "according to official sources" or the source name)
- Keep each section concise — 3-7 bullets max
`;
}

// ─── Data fetchers ────────────────────────────────────────────────────────────

function fetchAll(db) {
  return db.prepare(`
    SELECT * FROM articles
    WHERE passed_scoring = 1
      AND DATE(ingested_at) = DATE('now', 'localtime')
    ORDER BY relevance_score DESC, ingested_at ASC
  `).all();
}

function fetchByEventType(db, eventTypes, sector) {
  const placeholders = eventTypes.map(() => '?').join(',');
  return db.prepare(`
    SELECT * FROM articles
    WHERE passed_scoring = 1
      AND DATE(ingested_at) = DATE('now', 'localtime')
      AND event_type IN (${placeholders})
      AND (sector = ? OR sector = 'shared')
    ORDER BY relevance_score DESC
    LIMIT 15
  `).all(eventTypes, sector);
}

function formatArticle(a) {
  const body = a.body_translated || a.body || a.summary || '';
  const text = body.slice(0, 2000);
  const entities = a.entities ? JSON.parse(a.entities) : [];
  return [
    `Title: ${a.title || 'N/A'}`,
    `Source: ${a.source_name} [Tier ${a.tier}]`,
    `Event: ${a.event_type || 'N/A'}`,
    a.entities ? `Entities: ${entities.join(', ')}` : null,
    `Relevance: ${a.relevance_score}/10 — ${a.relevance_note || ''}`,
    `Body: ${text}`,
  ].filter(Boolean).join('\n');
}

// ─── LLM call ────────────────────────────────────────────────────────────────

async function generateBrief() {
  const db       = new Database(DB_PATH);
  const articles = fetchAll(db);
  db.close();

  if (articles.length === 0) {
    console.log('[ANALYST] No scored articles for today — skipping brief.');
    return null;
  }

  if (!API_KEY) {
    console.error('[ANALYST] LLM_API_KEY not set — cannot generate brief.');
    return `Daily Briefing — ${BRIEF_DATE}\n\nNo LLM API key configured. ${articles.length} articles scored but brief generation requires LLM_API_KEY.`;
  }

  // Build per-sector article lists
  const sectorArticles = {};
  for (const sector of SECTOR_LIST) {
    const tpl = SECTOR_TEMPLATES[sector];
    const sectionsMap = {};
    for (const section of tpl.sections) {
      sectionsMap[section.id] = fetchByEventType(db, getEventTypesForSection(section.id), sector);
    }
    sectorArticles[sector] = sectionsMap;
  }

  const formatted = {};
  for (const [sector, sections] of Object.entries(sectorArticles)) {
    formatted[sector] = {};
    for (const [sectionId, arts] of Object.entries(sections)) {
      formatted[sector][sectionId] = arts.map(formatArticle).join('\n\n---\n\n');
    }
  }

  // We re-open for the LLM call
  const db2     = new Database(DB_PATH);
  const allArts = fetchAll(db2);
  db2.close();

  const articlesText = allArts.map((a, i) => `--- Article ${i + 1} ---\n${formatArticle(a)}`).join('\n\n');
  const systemPrompt = buildBriefingSystemPrompt();
  const userPrompt   = `ARTICLES FOR TODAY:\n${articlesText}`;

  try {
    const resp = await openai.chat.completions.create({
      model: MODEL,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user',   content: userPrompt },
      ],
      max_tokens: 4096,
      temperature: 0,
    });

    const brief = resp.choices[0]?.message?.content?.trim();
    const filename = `data/brief-${BRIEF_DATE}.md`;
    fs.writeFileSync(path.resolve(__dirname, '../..', filename), brief, 'utf8');
    console.log(`[ANALYST] Brief saved to ${filename}`);
    return brief;

  } catch (err) {
    console.error(`[ANALYST] LLM error: ${err.message}`);
    return `Daily Briefing — ${BRIEF_DATE}\n\nError generating brief: ${err.message}\n\n${articles.length} articles were scored and are available in the database.`;
  }
}

// ─── Section → event type mapping (customize per deployment) ─────────────────

function getEventTypesForSection(sectionId) {
  const map = {
    prod:       ['production', 'disruption', 'pipeline', 'field-shutdown', 'new-discovery'],
    contracts:  ['contract', 'acquisition', 'deal-signed', 'expansion'],
    pricing:    ['pricing', 'revenue', 'market-move'],
    regulatory: ['political', 'regulatory', 'sanctions', 'legal'],
    macro:      ['macro-report', 'iea-outlook', 'opec', 'geopolitics'],
    fx:         ['fx-policy', 'monetary-policy', 'exchange-rate'],
    banking:    ['banking-regulation', 'banking-sector', 'sovereign-wealth'],
    liquidity:  ['liquidity', 'reserves', 'dollar-allocation'],
    regulation: ['banking-regulation', 'regulatory', 'cb-policy'],
  };
  return map[sectionId] || ['other'];
}

if (require.main === module) {
  generateBrief().catch(err => {
    console.error('[ANALYST] Fatal error:', err.message);
    process.exit(1);
  });
}

module.exports = { generateBrief };
