"""
Scraper module — fetches articles from RSS feeds and saves new ones to the DB.
"""
import time
import logging
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dateparser
from django.conf import settings
from django.db import transaction

from newsletter.models import Source, Article

logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'TechPulse/1.0 (IE University; Advanced Databases project)'}


def _ensure_sources():
    """Make sure Source rows exist for everything in settings."""
    for cfg in settings.SCRAPE_SOURCES:
        Source.objects.get_or_create(
            id=cfg['id'],
            defaults={
                'name': cfg['name'],
                'base_url': cfg['base_url'],
                'reliability_score': cfg['reliability_score'],
            },
        )


def _parse_date(entry):
    """Try to get a datetime from an RSS entry. Returns None if we can't."""
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


def _get_content(entry):
    """Pull the best body text we can find from an entry."""
    content_list = getattr(entry, 'content', None)
    if content_list:
        return content_list[0].get('value', '')
    return getattr(entry, 'summary', '') or ''


def _calc_importance(entry, source):
    """Quick heuristic score based on source reliability + whether there's actual content."""
    base = source.reliability_score
    has_body = bool(_get_content(entry).strip())
    return round(min(base + (0.05 if has_body else 0.0), 1.0), 3)


def scrape_source(source_cfg):
    """Scrape one source. Returns dict with found/new/error counts."""
    _ensure_sources()
    source = Source.objects.get(id=source_cfg['id'])
    feed_url = source_cfg['feed_url']

    try:
        feed = feedparser.parse(feed_url, request_headers=HEADERS)
    except Exception as e:
        logger.error('feedparser error for %s: %s', source.name, e)
        return {'found': 0, 'new': 0, 'error': str(e)}

    if feed.bozo and not feed.entries:
        err = str(getattr(feed, 'bozo_exception', 'parse error'))
        logger.warning('%s feed bozo: %s', source.name, err)
        return {'found': 0, 'new': 0, 'error': err}

    entries = feed.entries
    new_count = 0

    with transaction.atomic():
        for entry in entries:
            url = getattr(entry, 'link', None)
            if not url:
                continue
            if Article.objects.filter(url=url).exists():
                continue

            title = getattr(entry, 'title', '').strip()
            summary = getattr(entry, 'summary', '').strip()
            content = _get_content(entry).strip() or summary
            pub_date = _parse_date(entry)
            importance = _calc_importance(entry, source)

            Article.objects.create(
                source=source,
                title=title,
                summary=summary,
                content=content,
                url=url,
                importance_score=importance,
                published_at=pub_date,
                tagging_method='none',
            )
            new_count += 1

    logger.info('%s: %d found, %d new', source.name, len(entries), new_count)
    return {'found': len(entries), 'new': new_count, 'error': None}


def run_scraper(source_ids=None):
    """Run scraper for all sources (or a subset). Returns aggregate stats."""
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
        time.sleep(1)

    return {
        'sources_scraped': len(sources_cfg),
        'total_found': total_found,
        'total_new': total_new,
        'errors': errors,
    }
