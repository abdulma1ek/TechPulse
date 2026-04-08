-- TechPulse MySQL DDL
-- Advanced Databases · IE University
-- Run AFTER Django migrations: mysql -u root techpulse < schema.sql

-- ─────────────────────────────────────────────────────────
-- FULLTEXT INDEX
-- Powers keyword search across the article corpus
-- ─────────────────────────────────────────────────────────
ALTER TABLE articles ADD FULLTEXT INDEX ft_articles_title_content (title, content);


-- ─────────────────────────────────────────────────────────
-- TRIGGER
-- After every INSERT into article_tags, auto-increment
-- the usage_count counter on the corresponding tag row.
-- ─────────────────────────────────────────────────────────
DROP TRIGGER IF EXISTS after_article_tag_insert;

DELIMITER $$
CREATE TRIGGER after_article_tag_insert
    AFTER INSERT ON article_tags
    FOR EACH ROW
BEGIN
    UPDATE tags
    SET usage_count = usage_count + 1
    WHERE id = NEW.tag_id;
END$$
DELIMITER ;


-- ─────────────────────────────────────────────────────────
-- VIEW
-- recent_unplaced_articles: articles from the last 7 days
-- that have not yet been included in any newsletter edition.
-- ─────────────────────────────────────────────────────────
DROP VIEW IF EXISTS recent_unplaced_articles;

CREATE VIEW recent_unplaced_articles AS
    SELECT a.*
    FROM articles a
    WHERE a.ingested_at >= NOW() - INTERVAL 7 DAY
      AND a.id NOT IN (
          SELECT article_id FROM newsletter_articles
      );


-- ─────────────────────────────────────────────────────────
-- STORED PROCEDURE
-- newsletter_generate(edition_type)
-- Encapsulates the full filter-and-select logic for a given
-- edition type, creates the edition record, inserts matched
-- articles ordered by importance_score, and updates the count.
--
-- Edition types and their required tags:
--   general  → any article (no tag filter)
--   ai_only  → tag 'ai'
--   startups → tag 'startup' OR 'funding'
--   policy   → tag 'policy' OR 'regulation'
--   europe   → tag 'europe'
-- ─────────────────────────────────────────────────────────
DROP PROCEDURE IF EXISTS newsletter_generate;

DELIMITER $$
CREATE PROCEDURE newsletter_generate(IN p_edition_type VARCHAR(20))
BEGIN
    DECLARE v_newsletter_id INT;
    DECLARE v_window_start  DATETIME;
    DECLARE v_window_days   INT;
    DECLARE v_edition_name  VARCHAR(255);

    -- Determine the look-back window (policy uses 14 days, all others 7)
    SET v_window_days  = IF(p_edition_type = 'policy', 14, 7);
    SET v_window_start = NOW() - INTERVAL v_window_days DAY;
    SET v_edition_name = CONCAT(
        CASE p_edition_type
            WHEN 'general'  THEN 'General Tech'
            WHEN 'ai_only'  THEN 'AI Only'
            WHEN 'startups' THEN 'Startups & VC'
            WHEN 'policy'   THEN 'Policy & Reg.'
            WHEN 'europe'   THEN 'Europe Focus'
            ELSE p_edition_type
        END,
        ' — ',
        DATE_FORMAT(NOW(), '%Y-%m-%d')
    );

    -- Create the edition record
    INSERT INTO newsletter_editions
        (name, edition_type, generated_at, window_start, window_end, article_count)
    VALUES
        (v_edition_name, p_edition_type, NOW(), v_window_start, NOW(), 0);

    SET v_newsletter_id = LAST_INSERT_ID();

    -- Insert matching articles ordered by importance_score DESC
    -- ROW_NUMBER() window function assigns the position column
    INSERT INTO newsletter_articles (newsletter_id, article_id, position, section_summary)
    SELECT
        v_newsletter_id,
        ranked.article_id,
        ranked.pos,
        ''
    FROM (
        SELECT
            a.id AS article_id,
            ROW_NUMBER() OVER (ORDER BY a.importance_score DESC) AS pos
        FROM articles a
        JOIN article_tags at2 ON a.id = at2.article_id
        JOIN tags t           ON at2.tag_id = t.id
        WHERE a.ingested_at BETWEEN v_window_start AND NOW()
          AND (
              p_edition_type = 'general'
              OR (p_edition_type = 'ai_only'  AND t.tag_name = 'ai')
              OR (p_edition_type = 'startups' AND t.tag_name IN ('startup', 'funding'))
              OR (p_edition_type = 'policy'   AND t.tag_name IN ('policy', 'regulation'))
              OR (p_edition_type = 'europe'   AND t.tag_name = 'europe')
          )
        GROUP BY a.id
        ORDER BY a.importance_score DESC
        LIMIT 20
    ) AS ranked;

    -- Update article_count on the edition
    UPDATE newsletter_editions
    SET article_count = (
        SELECT COUNT(*) FROM newsletter_articles
        WHERE newsletter_id = v_newsletter_id
    )
    WHERE id = v_newsletter_id;

    -- Return the new edition id
    SELECT v_newsletter_id AS newsletter_id;
END$$
DELIMITER ;


-- ─────────────────────────────────────────────────────────
-- ADDITIONAL INDEXES
-- Supplement Django's auto-generated indexes for the filter
-- queries run inside the stored procedure.
-- ─────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_articles_published_at   ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_article_tags_tag_id     ON article_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_article_tags_article_id ON article_tags(article_id);
CREATE INDEX IF NOT EXISTS idx_articles_source_id      ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_ingested_at    ON articles(ingested_at);
CREATE INDEX IF NOT EXISTS idx_articles_importance     ON articles(importance_score);
