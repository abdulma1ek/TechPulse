"""
Tagging pipeline module.

Primary:  Claude LLM assigns tags with confidence scores (0.0–1.0).
Fallback: Keyword rules from the tag_rules table (confidence = 1.0).

Only tags with confidence >= settings.TAG_CONFIDENCE_THRESHOLD (0.5) are stored.

Usage:
    from newsletter.pipeline.tagger import run_tagger
    result = run_tagger(limit=50)
"""
import json
import logging
import time

import anthropic
from django.conf import settings
from django.db import transaction

from newsletter.models import Article, Tag, TagRule, ArticleTag

logger = logging.getLogger(__name__)

CONTROLLED_VOCABULARY = {
    'topic':        ['ai', 'hardware', 'software', 'security', 'policy', 'startup', 'funding', 'acquisition'],
    'geography':    ['us', 'europe', 'china', 'global'],
    'article_type': ['product-launch', 'research', 'analysis', 'funding-round', 'regulation'],
}

LLM_SYSTEM_PROMPT = """You are a news article tagger for a tech newsletter.
Given an article title and summary, assign relevant tags from the controlled vocabulary below.
Return ONLY a JSON array of objects with "tag" and "confidence" (0.0–1.0) fields.
Only include tags that clearly apply. Confidence >= 0.8 means highly relevant.

Controlled vocabulary:
- topic: ai, hardware, software, security, policy, startup, funding, acquisition
- geography: us, europe, china, global
- article_type: product-launch, research, analysis, funding-round, regulation

Example output:
[{"tag": "ai", "confidence": 0.95}, {"tag": "us", "confidence": 0.7}, {"tag": "funding-round", "confidence": 0.9}]

Return only the JSON array, no other text."""


def _build_article_text(article: Article) -> str:
    summary = article.summary or article.content[:500]
    return f"Title: {article.title}\nSummary: {summary}"


def tag_with_llm(article: Article) -> list[dict]:
    """
    Call Claude to assign tags to an article.
    Returns a list of {'tag': str, 'confidence': float} dicts (confidence >= threshold).
    Returns empty list on failure.
    """
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    threshold = settings.TAG_CONFIDENCE_THRESHOLD

    try:
        message = client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=512,
            messages=[
                {
                    'role': 'user',
                    'content': _build_article_text(article),
                }
            ],
            system=LLM_SYSTEM_PROMPT,
        )
        raw = message.content[0].text.strip()

        # Extract JSON array even if the model wraps it in markdown
        if '```' in raw:
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]

        results = json.loads(raw)
        if not isinstance(results, list):
            return []

        # Validate and filter
        valid_tags = {tag for tags in CONTROLLED_VOCABULARY.values() for tag in tags}
        return [
            r for r in results
            if isinstance(r, dict)
            and r.get('tag') in valid_tags
            and isinstance(r.get('confidence'), (int, float))
            and float(r['confidence']) >= threshold
        ]

    except json.JSONDecodeError as exc:
        logger.warning('LLM returned invalid JSON for article %s: %s', article.id, exc)
        return []
    except anthropic.APIError as exc:
        logger.error('Anthropic API error for article %s: %s', article.id, exc)
        return []
    except Exception as exc:
        logger.error('Unexpected LLM error for article %s: %s', article.id, exc)
        return []


def tag_with_rules(article: Article) -> list[dict]:
    """
    Apply keyword rules from the tag_rules table.
    Returns a list of {'tag': str, 'confidence': float, 'rule': True} dicts.
    """
    rules = TagRule.objects.select_related('tag').all()
    matched_tags: dict[str, float] = {}

    text_map = {
        'title': article.title.lower(),
        'content': (article.content or article.summary or '').lower(),
    }

    for rule in rules:
        text = text_map.get(rule.match_field, '')
        if rule.keyword.lower() in text:
            tag_name = rule.tag.tag_name
            # Keep highest priority match if the same tag matched multiple rules
            if tag_name not in matched_tags:
                matched_tags[tag_name] = 1.0

    return [{'tag': tag, 'confidence': 1.0} for tag in matched_tags]


def _save_tags(article: Article, tag_results: list[dict], assigned_by: str) -> int:
    """Persist ArticleTag rows and return count of tags saved."""
    if not tag_results:
        return 0

    tag_names = [r['tag'] for r in tag_results]
    tags_by_name = {t.tag_name: t for t in Tag.objects.filter(tag_name__in=tag_names)}

    saved = 0
    for result in tag_results:
        tag = tags_by_name.get(result['tag'])
        if not tag:
            continue
        ArticleTag.objects.get_or_create(
            article=article,
            tag=tag,
            defaults={
                'confidence': round(float(result['confidence']), 4),
                'assigned_by': assigned_by,
            },
        )
        saved += 1

    return saved


def tag_article(article: Article) -> dict:
    """
    Tag a single article: try LLM first, fall back to rules.
    Updates article.tagging_method and saves.
    Returns {'method': str, 'tags_saved': int}.
    """
    with transaction.atomic():
        # Primary: LLM
        llm_results = tag_with_llm(article)
        if llm_results:
            saved = _save_tags(article, llm_results, 'llm')
            article.tagging_method = 'llm'
            article.save(update_fields=['tagging_method'])
            return {'method': 'llm', 'tags_saved': saved}

        # Fallback: keyword rules
        rule_results = tag_with_rules(article)
        if rule_results:
            saved = _save_tags(article, rule_results, 'rules')
            article.tagging_method = 'rules'
            article.save(update_fields=['tagging_method'])
            return {'method': 'rules', 'tags_saved': saved}

        # No tags found
        article.tagging_method = 'none'
        article.save(update_fields=['tagging_method'])
        return {'method': 'none', 'tags_saved': 0}


def run_tagger(limit: int = 50, method: str = 'auto') -> dict:
    """
    Tag up to `limit` untagged articles.
    method: 'auto' (LLM + fallback), 'llm' (LLM only), 'rules' (rules only)
    Returns aggregate stats.
    """
    articles = Article.objects.filter(tagging_method='none').order_by('ingested_at')[:limit]
    articles = list(articles)

    llm_count = 0
    rules_count = 0
    none_count = 0

    for article in articles:
        if method == 'rules':
            results = tag_with_rules(article)
            if results:
                _save_tags(article, results, 'rules')
                article.tagging_method = 'rules'
                article.save(update_fields=['tagging_method'])
                rules_count += 1
            else:
                none_count += 1
        elif method == 'llm':
            results = tag_with_llm(article)
            if results:
                _save_tags(article, results, 'llm')
                article.tagging_method = 'llm'
                article.save(update_fields=['tagging_method'])
                llm_count += 1
            else:
                none_count += 1
        else:
            result = tag_article(article)
            if result['method'] == 'llm':
                llm_count += 1
            elif result['method'] == 'rules':
                rules_count += 1
            else:
                none_count += 1

        time.sleep(0.2)  # rate limit for LLM calls

    return {
        'processed': len(articles),
        'llm_tagged': llm_count,
        'rules_tagged': rules_count,
        'untagged': none_count,
    }
