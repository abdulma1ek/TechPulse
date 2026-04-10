# TechPulse

Database-driven tech newsletter system built with Django and MySQL. Scrapes articles from RSS feeds, tags them using Claude AI + keyword rules, and generates curated newsletter editions via a stored procedure.

Built for Advanced Databases (IE University).

## Setup

Requires Python 3.11+, MySQL 8.0+, and an Anthropic API key for LLM tagging.

```bash
python -m venv venv
source venv/bin/activate   # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

Copy the env file and fill in your credentials:
```bash
cp .env.example .env
```

Create the MySQL database:
```sql
CREATE DATABASE techpulse CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Run Django migrations, then apply the extra schema (triggers, views, stored proc):
```bash
python manage.py migrate
mysql -u root techpulse < schema.sql
```

## Running the pipeline

```bash
# 1. seed the tag vocabulary and keyword rules
python manage.py seed_tags

# 2. scrape articles from RSS feeds
python manage.py scrape

# 3. tag articles (Claude + keyword fallback)
python manage.py tag --limit 50

# 4. generate a newsletter edition
python manage.py generate_edition --type ai_only
```

Then visit http://localhost:8000 for the dashboard:
```bash
python manage.py runserver
```

## Edition types

- `general` — all articles
- `ai_only` — AI/ML articles only
- `startups` — startup + funding tagged
- `policy` — regulation + policy tagged
- `europe` — europe-tagged articles
- Policy editions look back 14 days, everything else 7

## Project structure

- `newsletter/` — Django app (models, views, templates, pipeline)
- `newsletter/pipeline/` — scraper, tagger, newsletter generation logic
- `newsletter/management/commands/` — CLI commands for the pipeline
- `techpulse/` — Django project settings
- `schema.sql` — MySQL triggers, views, stored procedure, extra indexes
- `analytics.sql` — deliverable queries (window functions, fulltext search, etc.)
- `sentinel-master/` — Node.js scraper module (separate component)

## Key database features

- **Stored procedure** (`newsletter_generate`) — handles edition creation + article selection
- **Trigger** — auto-increments `usage_count` on tags when articles are tagged
- **View** (`recent_unplaced_articles`) — articles not yet in any edition
- **Fulltext index** — enables natural language and boolean search on articles
- **Window functions** — used in analytics queries for ranking and running totals
