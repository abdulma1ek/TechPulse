"""
Newsletter generation pipeline module.

Calls the MySQL stored procedure `newsletter_generate(edition_type)` to
create a new NewsletterEdition and populate newsletter_articles.

Also provides a renderer that formats an edition as plain HTML for display.

Usage:
    from newsletter.pipeline.newsletter import generate_edition, render_edition
    edition = generate_edition('ai_only')
    html = render_edition(edition)
"""
import logging

from django.db import connection

from newsletter.models import NewsletterEdition, NewsletterArticle

logger = logging.getLogger(__name__)

EDITION_LABELS = {
    'general':  'General Tech',
    'ai_only':  'AI Only',
    'startups': 'Startups & VC',
    'policy':   'Policy & Reg.',
    'europe':   'Europe Focus',
}

VALID_EDITION_TYPES = list(EDITION_LABELS.keys())


def generate_edition(edition_type: str) -> NewsletterEdition:
    """
    Call the `newsletter_generate` stored procedure for the given edition type
    and return the newly created NewsletterEdition instance.
    """
    if edition_type not in VALID_EDITION_TYPES:
        raise ValueError(
            f"Invalid edition type '{edition_type}'. "
            f"Valid options: {VALID_EDITION_TYPES}"
        )

    with connection.cursor() as cursor:
        cursor.callproc('newsletter_generate', [edition_type])
        # The procedure returns SELECT v_newsletter_id AS newsletter_id
        row = cursor.fetchone()

    if not row:
        raise RuntimeError(f'newsletter_generate returned no result for edition_type={edition_type}')

    newsletter_id = row[0]
    edition = NewsletterEdition.objects.get(pk=newsletter_id)
    logger.info(
        'Generated edition: %s (id=%s, articles=%s)',
        edition.name, edition.pk, edition.article_count,
    )
    return edition


def render_edition(edition: NewsletterEdition) -> str:
    """
    Render a newsletter edition as an HTML string.
    Articles are grouped by their tag type into sections.
    """
    newsletter_articles = (
        NewsletterArticle.objects
        .filter(newsletter=edition)
        .select_related('article__source')
        .prefetch_related('article__article_tags__tag')
        .order_by('position')
    )

    lines = [
        f'<h1>{edition.name}</h1>',
        f'<p class="meta">Generated: {edition.generated_at.strftime("%Y-%m-%d %H:%M UTC")} &nbsp;|&nbsp; '
        f'Articles: {edition.article_count} &nbsp;|&nbsp; '
        f'Window: {edition.window_start.strftime("%Y-%m-%d")} – {edition.window_end.strftime("%Y-%m-%d")}</p>',
        '<hr>',
    ]

    for na in newsletter_articles:
        article = na.article
        tags = [at.tag.tag_name for at in article.article_tags.all()]
        tag_html = ' '.join(f'<span class="tag">{t}</span>' for t in tags)

        source_name = article.source.name if article.source else ''
        pub_date = article.published_at.strftime('%Y-%m-%d') if article.published_at else ''

        lines.append(f'''
<div class="article">
  <h3><a href="{article.url}" target="_blank">{article.title}</a></h3>
  <p class="meta">{source_name}{" · " + pub_date if pub_date else ""} &nbsp;|&nbsp; Score: {article.importance_score or "—"}</p>
  <p class="summary">{article.summary or ""}</p>
  <p class="tags">{tag_html}</p>
</div>
''')

    return '\n'.join(lines)
