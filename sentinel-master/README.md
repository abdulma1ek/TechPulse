# Sentinel

> Autonomous multi-source intelligence pipeline. Scrapes, scores, translates, and synthesizes news into sector-specific briefing documents — fully configurable for any industry vertical.

[![Node.js](https://img.shields.io/badge/node-%3E%3D18-brightgreen)](package.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What it does

Sentinel runs a fully autonomous daily pipeline:

```
RSS / HTML / PDF → Translate → Score → Synthesize → Daily Briefing
```

Each stage is plug-and-play. Swap in new sources, adjust scoring thresholds, or add new sectors — without touching the core engine.

## Architecture

```
sources/registry.json     ← Your source configuration
        │
        ▼
┌───────────────────────┐
│   RSS Scraper         │  ← feeds, websites, PDFs
│   HTML Scraper        │
│   PDF Scraper         │
└─────────┬─────────────┘
          │ raw articles
          ▼
┌───────────────────────┐
│     Translator        │  ← LLM-powered translation (Arabic → English etc.)
└─────────┬─────────────┘
          │ translated text
          ▼
┌───────────────────────┐
│      Scorer           │  ← relevance filtering, sector scoring, entity extraction
└─────────┬─────────────┘
          │ scored articles
          ▼
┌───────────────────────┐
│      Analyst          │  ← LLM synthesis into structured briefing
└─────────┬─────────────┘
          │ final brief
          ▼
  Discord / Slack / File
```

## Features

- **Multi-format scraping** — RSS feeds, HTML pages, PDF reports
- **LLM translation** — handles non-English sources via OpenAI-compatible API
- **Relevance scoring** — configurable sector prompts, auto-tier1 for official sources
- **Multi-sector support** — a single pipeline can score one article across multiple sectors
- **Audit trail** — JSONL pipeline logs with per-source success/failure tracking
- **SQLite persistence** — deduplication, seen-url tracking, article history
- **Flexible output** — Discord webhook, file export, or custom hook

## Quick start

### Prerequisites

- Node.js ≥ 18
- SQLite (included in the `better-sqlite3` native binding)
- An LLM API key (OpenAI, Anthropic, DeepSeek, MiniMax, or any OpenAI-compatible endpoint)

### Install

```bash
git clone https://github.com/<you>/sentinel.git
cd sentinel
npm install
```

### Configure

**1. Add your sources** — edit `sources/registry.json`:

```json
{
  "sources": [
    {
      "id": "my-feed",
      "name": "My Industry Feed",
      "url": "https://example.com/feed.xml",
      "method": "rss",
      "tier": 3,
      "sector": "my-sector",
      "language": "en",
      "active": true
    }
  ]
}
```

**2. Set your API key** — create `.env` in the project root:

```env
# Required for the scoring stage
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1   # omit for OpenAI defaults
LLM_MODEL=gpt-4o-mini                      # defaults to gpt-4o-mini
```

**3. Initialize the database:**

```bash
node data/init-db.js
```

**4. Run the pipeline:**

```bash
# Full pipeline: scrape → score → end-of-day brief
node sentinel.js eod

# Scrape only (no brief)
node sentinel.js scrape

# End-of-day brief from existing articles (no scrape)
node sentinel.js brief-only

# Scrape only tier 2 sources
node sentinel.js scrape-t2
```

## Adding a new sector

Sentinel is sector-agnostic. To add a new sector (e.g. `banking`):

**1. Add sector sources to `registry.json`** with `sector: "banking"`

**2. Add a scoring prompt in `src/scorer/scorer.js`:**

```javascript
const SECTOR_PROMPTS = {
  oil:      `...`, // already present
  banking: `You are an analyst scoring articles for the banking sector.
             Score 0-10 based on relevance to [your sector]...
             Respond with valid JSON: { relevance_score, relevance_note, event_type, entities }`,
};
```

**3. Register it in `ACTIVE_SECTORS`:**

```javascript
const ACTIVE_SECTORS = ['oil', 'banking'];
```

**4. Optionally add a briefing template in `src/analyst/analyst.js`** for sector-specific structure.

## Project structure

```
sentinel/
├── sentinel.js              # Pipeline orchestrator
├── package.json
├── .env.example
├── sources/
│   └── registry.json        # Source definitions (RSS, HTML, PDF)
├── src/
│   ├── scraper/
│   │   ├── rss.js           # RSS feed scraper
│   │   ├── html.js          # HTML page scraper
│   │   └── pdf.js           # PDF report scraper
│   ├── translator/
│   │   └── translator.js    # LLM translation stage
│   ├── scorer/
│   │   └── scorer.js       # Relevance scoring + entity extraction
│   └── analyst/
│       └── analyst.js       # Brief synthesis
└── data/
    ├── init-db.js           # Database setup script
    └── sentinel.sqlite      # SQLite database (created at init)
```

## Configuration reference

### Source registry (`sources/registry.json`)

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique source identifier |
| `name` | string | Human-readable name |
| `url` | string | Feed or page URL |
| `method` | string | `rss`, `html`, or `pdf` |
| `tier` | integer | 1 (official, auto-pass) / 2 (trusted) / 3 (general) |
| `sector` | string | Sector ID this source belongs to |
| `language` | string | ISO 639-1 language code |
| `active` | boolean | Whether to include in scraping runs |
| `category` | string | `official`, `news`, `report` |

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LLM_API_KEY` | Yes | — | API key for scoring and translation |
| `LLM_BASE_URL` | No | OpenAI | Base URL for OpenAI-compatible API |
| `LLM_MODEL` | No | `gpt-4o-mini` | Model to use for scoring/translation |
| `DISCORD_WEBHOOK_URL` | No | — | Discord webhook for brief delivery |
| `DISCORD_CHANNEL_ID` | No | — | Channel ID for Discord delivery |

## Extending the pipeline

Each stage is a standalone module that exports a single async function. To add a custom stage:

```javascript
// src/my-stage.js
async function runMyStage() {
  // your logic here
  return { customField: 'result' };
}

// Add to the pipeline in sentinel.js:
stages.myStage = await runStage('My Stage', runMyStage);
```

## License

MIT
