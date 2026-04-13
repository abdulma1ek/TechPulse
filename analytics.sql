-- TechPulse Analytics Queries
-- Advanced Databases, IE University
-- Deliverable 5: window functions, source coverage, tagging comparison, fulltext search


-- 1. Top tags by week (window functions)
-- Shows each tag's count per week, total tags that week, and rank within the week
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


-- 2. Source coverage (last 7 days)
-- Articles per source, avg importance, and what % got tagged
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


-- 3. Tagging method comparison (LLM vs keyword rules)
-- Overall stats
SELECT
    at2.assigned_by,
    COUNT(*)                            AS total_tag_assignments,
    AVG(at2.confidence)                 AS avg_confidence,
    COUNT(DISTINCT at2.article_id)      AS articles_tagged,
    COUNT(DISTINCT at2.tag_id)          AS distinct_tags_used
FROM article_tags at2
GROUP BY at2.assigned_by;

-- Broken down by tag type
SELECT
    at2.assigned_by,
    t.tag_type,
    COUNT(*)                            AS assignments,
    AVG(at2.confidence)                 AS avg_confidence
FROM article_tags at2
JOIN tags t ON at2.tag_id = t.id
GROUP BY at2.assigned_by, t.tag_type
ORDER BY at2.assigned_by, t.tag_type;


-- 4. Fulltext search examples
-- Natural language mode
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

-- Boolean mode (exact phrase + exclusion)
SELECT
    a.id,
    a.title,
    a.published_at
FROM articles a
WHERE MATCH(a.title, a.content)
    AGAINST ('+OpenAI -layoffs' IN BOOLEAN MODE)
ORDER BY a.published_at DESC
LIMIT 10;


-- 5. Recent unplaced articles (uses the view we created in schema.sql)
SELECT
    r.id,
    r.title,
    r.importance_score,
    r.tagging_method,
    r.ingested_at
FROM recent_unplaced_articles r
ORDER BY r.importance_score DESC
LIMIT 20;


-- 6. Newsletter edition summary with running totals (window function)
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


-- 7. Tag usage rankings
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
