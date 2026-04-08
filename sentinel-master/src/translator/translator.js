'use strict';

const path     = require('path');
const Database = require('better-sqlite3');
const OpenAI  = require('openai');

const DB_PATH    = path.resolve(__dirname, '../../data/sentinel.sqlite');
const MODEL     = process.env.LLM_MODEL       || 'gpt-4o-mini';
const BASE_URL  = process.env.LLM_BASE_URL   || 'https://api.openai.com/v1';
const API_KEY   = process.env.LLM_API_KEY;

const openai = new OpenAI({
  apiKey:  API_KEY,
  baseURL: BASE_URL,
});

const SYSTEM_PROMPT = `You are a professional news translator. Translate the article body below to English.
Preserve all factual information, numbers, names, and dates exactly.
Only translate the body text, not the metadata.
Respond with the full translated text and nothing else.`;

const TARGET_LANGS = ['ar', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'zh'];

function prepareStatements(db) {
  return {
    getUntranslated: db.prepare(`
      SELECT * FROM articles
      WHERE body IS NOT NULL
        AND body_translated IS NULL
        AND language_orig IN (${TARGET_LANGS.map(() => '?').join(',')})
        AND passed_scoring = 0
      ORDER BY ingested_at ASC
      LIMIT 20
    `),
    updateTranslation: db.prepare(`
      UPDATE articles SET body_translated = @body_translated WHERE id = @id
    `),
  };
}

async function runTranslator() {
  if (!API_KEY) {
    console.error('[TRANSLATOR] LLM_API_KEY not set — skipping translation stage.');
    return;
  }

  const db     = new Database(DB_PATH);
  const stmts  = prepareStatements(db);
  const rows   = stmts.getUntranslated.all(TARGET_LANGS);

  console.log(`[TRANSLATOR] ${rows.length} articles to translate`);

  for (const article of rows) {
    if (!article.body) continue;

    try {
      const resp = await openai.chat.completions.create({
        model: MODEL,
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user',   content: article.body.slice(0, 8000) },
        ],
        max_tokens: 2048,
        temperature: 0,
      });

      const translated = resp.choices[0]?.message?.content?.trim() || null;
      stmts.updateTranslation.run({ id: article.id, body_translated: translated });
      console.log(`[TRANSLATOR] ${article.id} — translated (${article.language_orig} → en)`);

    } catch (err) {
      console.error(`[TRANSLATOR] ${article.id} — ERROR: ${err.message}`);
    }

    await new Promise(r => setTimeout(r, 300));
  }

  db.close();
  console.log('[TRANSLATOR] Done.');
}

if (require.main === module) {
  runTranslator().catch(err => {
    console.error('[TRANSLATOR] Fatal error:', err.message);
    process.exit(1);
  });
}

module.exports = { runTranslator };
