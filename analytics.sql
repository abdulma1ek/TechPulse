-- TechPulse Analytics Queries
-- Advanced Databases · IE University
-- Deliverable 5: window functions, source coverage, tagging comparison, FULLTEXT search

-- ─────────────────────────────────────────────────────────
-- 1. TOP TAGS BY WEEK  (Window Functions)
--    For each week, shows each tag's count, total tags that
--    week, and the tag's rank within that week.
-- ─────────────────────────────────────────────────────────
SELECT
    t.tag_name,
    t.tag_type,
    DATE_FORMAT(a.ingested_at, '%x-W%v')              AS iso_week,
    COUNT(*)                                           AS tag_count,
    SUM(COUNT(*)) OVER (
        PARTITION BY DATE_FORMAT(a.ingested_at, '%x-W%v')
    )                                                  AS total_tags_that_week,
    RANK() OVER (
        PARTITION BY DATE_FORMAT(a.ingested_at, '%x-W%v')
        ORDER BY COUNT(*) DESC
    )                                                  AS week_rank
FROM article_tags  at2
JOIN tags           t  ON at2.tag_id   = t.id
JOIN articles       a  ON at2.article_id = a.id
GROUP BY t.tag_name, t.tag_type, iso_week
ORDER BY iso_week DESC, week_rank;


-- ─────────────────────────────────────────────────────────
-- 2. SOURCE COVERAGE
--    Articles per source in the last 7 days, with average
--    importance score and tagging rate.
-- ─────────────────────────────────────────────────────────
SELECT
    s.name                              AS source_name,
    s.reliability_score,
    COUNT(a.id)                         AS articles_last_7_days,
    AVG(a.importance_score)             AS avg_importance,
    SUM(CASE WHEN a.tagging_method <> 'none' THEN 1 ELSE 0 END) AS tagged_count,
    ROUND(
        100.0 * SUM(CASE WHEN a.tagging_method <> 'none' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(a.id), 0), 1
    )                                   AS tagging_rate_pct
FROM sources s
LEFT JOIN articles a
       ON s.id = a.source_id
      AND a.ingested_at >= NOW() - INTERVAL 7 DAY
GROUP BY s.id
ORDER BY articles_last_7_days DESC;


-- ─────────────────────────────────────────────────────────
-- 3. TAGGING METHOD COMPARISON
--    LLM vs keyword rules: total tags, average confidence,
--    distinct articles tagged, and tag type breakdown.
-- ─────────────────────────────────────────────────────────
SELECT
    at2.assigned_by,
    COUNT(*)                            AS total_tag_assignments,
    AVG(at2.confidence)                 AS avg_confidence,
    COUNT(DISTINCT at2.article_id)      AS articles_tagged,
    COUNT(DISTINCT at2.tag_id)          AS distinct_tags_used
FROM article_tags at2
GROUP BY at2.assigned_by;

-- Per-type breakdown
SELECT
    at2.assigned_by,
    t.tag_type,
    COUNT(*)                            AS assignments,
    AVG(at2.confidence)                 AS avg_confidence
FROM article_tags at2
JOIN tags t ON at2.tag_id = t.id
GROUP BY at2.assigned_by, t.tag_type
ORDER BY at2.assigned_by, t.tag_type;


-- ─────────────────────────────────────────────────────────
-- 4. FULLTEXT SEARCH
--    Uses the FULLTEXT INDEX ft_articles_title_content.
--    Replace the search term as needed.
-- ─────────────────────────────────────────────────────────
SELECT
    a.id,
    a.title,
    s.name                              AS source,
    a.published_at,
    MATCH(a.title, a.content)
        AGAINST ('artificial intelligence' IN NATURAL LANGUAGE MODE) AS relevance_score
FROM articles a
JOIN sources s ON a.source_id = s.id
WHERE MATCH(a.title, a.content)
    AGAINST ('artificial intelligence' IN NATURAL LANGUAGE MODE)
ORDER BY relevance_score DESC
LIMIT 20;

-- Boolean mode search example (exact phrase + exclusion)
SELECT
    a.id,
    a.title,
    a.published_at
FROM articles a
WHERE MATCH(a.title, a.content)
    AGAINST ('+OpenAI -layoffs' IN BOOLEAN MODE)
ORDER BY a.published_at DESC
LIMIT 10;


-- ─────────────────────────────────────────────────────────
-- 5. RECENT UNPLACED ARTICLES  (via VIEW)
--    Articles from the last 7 days not yet in any edition.
-- ─────────────────────────────────────────────────────────
SELECT
    r.id,
    r.title,
    r.importance_score,
    r.tagging_method,
    r.ingested_at
FROM recent_unplaced_articles r
ORDER BY r.importance_score DESC
LIMIT 20;


-- ─────────────────────────────────────────────────────────
-- 6. NEWSLETTER EDITION SUMMARY
--    Overview of all generated editions with article counts
--    and running total using a window function.
-- ─────────────────────────────────────────────────────────
SELECT
    ne.id,
    ne.name,
    ne.edition_type,
    ne.article_count,
    ne.generated_at,
    SUM(ne.article_count) OVER (
        PARTITION BY ne.edition_type
        ORDER BY ne.generated_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                   AS cumulative_articles,
    RANK() OVER (
        PARTITION BY ne.edition_type
        ORDER BY ne.article_count DESC
    )                                   AS rank_by_size
FROM newsletter_editions ne
ORDER BY ne.generated_at DESC;


-- ─────────────────────────────────────────────────────────
-- 7. TAG USAGE GROWTH OVER TIME
--    How usage_count has evolved per tag (from trigger increments).
-- ─────────────────────────────────────────────────────────
SELECT
    t.tag_name,
    t.tag_type,
    t.usage_count,
    RANK() OVER (ORDER BY t.usage_count DESC)   AS overall_rank,
    RANK() OVER (
        PARTITION BY t.tag_type
        ORDER BY t.usage_count DESC
    )                                            AS rank_within_type
FROM tags t
ORDER BY t.usage_count DESC;
