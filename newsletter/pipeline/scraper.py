"""
Scraper pipeline module.

Fetches articles from the 4 TechPulse sources via RSS feeds,
deduplicates by URL, and persists to the articles table.

Usage:
    from newsletter.pipeline.scraper import run_scraper
    result = run_scraper()
"""
import hashlib
import time
import logging
from datetime import datetime, timezone

import feedparser
import requests
from dateutil import parser as dateparser
from django.conf import settings
from django.db import transaction

from newsletter.models import Source, Article

logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'TechPulse/1.0 (IE University Advanced Databases project; +https://github.com)'
}
REQUEST_TIMEOUT = 30


def _ensure_sources():
    """Create Source rows from settings.SCRAPE_SOURCES if they don't exist yet."""
    for cfg in settings.SCRAPE_SOURCES:
        Source.objects.get_or_create(
            id=cfg['id'],
            defaults={
                'name': cfg['name'],
                'base_url': cfg['base_url'],
                'reliability_score': cfg['reliability_score'],
            },
        )


def _parse_date(entry) -> datetime | None:
    """Return a timezone-aware datetime from an RSS entry, or None."""
    for attr in ('published_parsed', 'updated_parsed'):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for attr in ('published', 'updated'):
        val = getattr(entry, attr, None)
        if val:
            try:
                return dateparser.parse(val).astimezone(timezone.utc)
            except Exception:
                pass
    return None


def _get_content(entry) -> str:
    """Extract the best available body text from an RSS entry."""
    # Try full content first
    content_list = getattr(entry, 'content', None)
    if content_list:
        return content_list[0].get('value', '')
    # Fall back to summary
    return getattr(entry, 'summary', '') or ''


def _importance_score(entry, source: Source) -> float:
    """
    Simple heuristic importance score (0.0–1.0) based on source reliability
    and whether the entry has a full content body.
    """
    base = source.reliability_score
    has_content = bool(_get_content(entry).strip())
    return round(min(base + (0.05 if has_content else 0.0), 1.0), 3)


def scrape_source(source_cfg: dict) -> dict:
    """
    Scrape a single source RSS feed and persist new articles.
    Returns a dict with counts: {'found': N, 'new': N, 'error': None|str}
    """
    _ensure_sources()
    source = Source.objects.get(id=source_cfg['id'])
    feed_url = source_cfg['feed_url']

    try:
        feed = feedparser.parse(
            feed_url,
            request_headers=HEADERS,
        )
    except Exception as exc:
        logger.error('feedparser error for %s: %s', source.name, exc)
        return {'found': 0, 'new': 0, 'error': str(exc)}

    if feed.bozo and not feed.entries:
        err = str(getattr(feed, 'bozo_exception', 'unknown parse error'))
        logger.warning('Feed %s bozo: %s', source.name, err)
        return {'found': 0, 'new': 0, 'error': err}

    entries = feed.entries
    new_count = 0

    with transaction.atomic():
        for entry in entries:
            url = getattr(entry, 'link', None)
            if not url:
                continue

            # Deduplicate
            if Article.objects.filter(url=url).exists():
                continue

            title = getattr(entry, 'title', '').strip()
            summary = getattr(entry, 'summary', '').strip()
            content = _get_content(entry).strip() or summary
            published_at = _parse_date(entry)
            importance = _importance_score(entry, source)

            Article.objects.create(
                source=source,
                title=title,
                summary=summary,
                content=content,
                url=url,
                importance_score=importance,
                published_at=published_at,
                tagging_method='none',
            )
            new_count += 1

    logger.info('%s: found=%d new=%d', source.name, len(entries), new_count)
    return {'found': len(entries), 'new': new_count, 'error': None}


def run_scraper(source_ids: list[int] | None = None) -> dict:
    """
    Run the scraper for all sources (or a subset by id).
    Returns aggregate stats.
    """
    _ensure_sources()
    sources_cfg = settings.SCRAPE_SOURCES
    if source_ids:
        sources_cfg = [s for s in sources_cfg if s['id'] in source_ids]

    total_found = 0
    total_new = 0
    errors = []

    for cfg in sources_cfg:
        result = scrape_source(cfg)
        total_found += result['found']
        total_new += result['new']
        if result['error']:
            errors.append(f"{cfg['name']}: {result['error']}")
        time.sleep(1)  # polite delay between sources

    return {
        'sources_scraped': len(sources_cfg),
        'total_found': total_found,
        'total_new': total_new,
        'errors': errors,
    }
