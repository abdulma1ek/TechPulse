'use strict';

require('dotenv').config();

const {
  runRssScraper,
} = require('./src/scraper/rss');
const {
  runHtmlScraper,
} = require('./src/scraper/html');
const {
  runPdfScraper,
} = require('./src/scraper/pdf');
const {
  runTranslator,
} = require('./src/translator/translator');
const {
  runScorer,
} = require('./src/scorer/scorer');
const {
  generateBrief,
} = require('./src/analyst/analyst');

// ─── Config ───────────────────────────────────────────────────────────────────

const DISCORD_WEBHOOK_URL = process.env.DISCORD_WEBHOOK_URL;
const DISCORD_CHANNEL_ID  = process.env.DISCORD_CHANNEL_ID;

// ─── Helpers ───────────────────────────────────────────────────────────────────

function log(stage, msg) {
  console.log(`[${stage}] ${msg}`);
}

async function runStage(name, fn, ...args) {
  log(name, 'Starting...');
  const start = Date.now();
  try {
    const result = await fn(...args);
    log(name, `Done in ${Date.now() - start}ms`);
    return result;
    } catch (err) {
    log(name, `ERROR: ${err.message}`);
    throw err;
  }
}

async function sendToDiscord(content) {
  if (!DISCORD_WEBHOOK_URL) return;
  const { default: axios } = await import('axios');
  try {
    await axios.post(DISCORD_WEBHOOK_URL, { content });
    log('DISCORD', 'Brief sent');
  } catch (err) {
    log('DISCORD', `Failed to send: ${err.message}`);
  }
}

async function sendMultiPart(content, chunks) {
  if (!DISCORD_WEBHOOK_URL) return;
  const { default: axios } = await import('axios');

  const payload = {
    content,
    components: chunks.length > 1 ? [{
      type: 1,
      components: [{
        type: 2,
        label: 'View Full Brief',
        style: 5,
        url: `file://${process.cwd()}/data/brief-${new Date().toISOString().slice(0, 10)}.md`,
      }],
    }] : undefined,
  };

  try {
    await axios.post(DISCORD_WEBHOOK_URL, payload);
  } catch (err) {
    log('DISCORD', `Failed: ${err.message}`);
  }
}

// ─── Stages ───────────────────────────────────────────────────────────────────

async function scrapeAll() {
  await runStage('RSS', runRssScraper);
  await runStage('HTML', runHtmlScraper);
  await runStage('PDF', runPdfScraper);
}

async function scrapeTier2() {
  await runStage('RSS-T2', () => runRssScraper(2));
}

// ─── CLI Modes ────────────────────────────────────────────────────────────────

const [,, mode = 'eod'] = process.argv;

(async () => {
  console.log(`\n=== Sentinel | mode: ${mode} ===\n`);

  switch (mode) {
    case 'scrape': {
      await scrapeAll();
      break;
    }

    case 'scrape-t2': {
      await scrapeTier2();
      break;
    }

    case 'brief-only': {
      const brief = await runStage('ANALYST', generateBrief);
      if (brief) {
        await sendToDiscord(brief.slice(0, 2000));
      }
      break;
    }

    case 'eod':
    default: {
      await scrapeAll();
      await runStage('TRANSLATOR', runTranslator);
      await runStage('SCORER', runScorer);
      const brief = await runStage('ANALYST', generateBrief);
      if (brief) {
        const CHUNK_SIZE = 1990;
        const chunks = [];
        for (let i = 0; i < brief.length; i += CHUNK_SIZE) {
          chunks.push(brief.slice(i, i + CHUNK_SIZE));
        }
        if (chunks.length === 1) {
          await sendToDiscord(chunks[0]);
        } else {
          for (const chunk of chunks) {
            await sendToDiscord(chunk);
            await new Promise(r => setTimeout(r, 1000));
          }
        }
      }
      break;
    }
  }

  console.log('\n=== Sentinel | Complete ===\n');
})();
