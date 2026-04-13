-- TechPulse schema extensions
-- Run after Django migrations: mysql -u root techpulse < schema.sql
-- These add fulltext search, triggers, views, stored procs that Django doesn't handle natively

-- fulltext index for article search
ALTER TABLE articles ADD FULLTEXT INDEX ft_articles_title_content (title, content);


-- auto-increment tag usage_count when a new article_tag is inserted
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


-- view: articles from last 7 days not yet placed in any newsletter
DROP VIEW IF EXISTS recent_unplaced_articles;

CREATE VIEW recent_unplaced_articles AS
    SELECT a.*
    FROM articles a
    WHERE a.ingested_at >= NOW() - INTERVAL 7 DAY
      AND a.id NOT IN (
          SELECT article_id FROM newsletter_articles
      );


-- stored procedure: generate a newsletter edition
-- picks articles matching the edition type's tags, ordered by importance
DROP PROCEDURE IF EXISTS newsletter_generate;

DELIMITER $$
CREATE PROCEDURE newsletter_generate(IN p_edition_type VARCHAR(20))
BEGIN
    DECLARE v_newsletter_id INT;
    DECLARE v_window_start  DATETIME;
    DECLARE v_window_days   INT;
    DECLARE v_edition_name  VARCHAR(255);

    -- policy editions look back 14 days, everything else 7
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

    INSERT INTO newsletter_editions
        (name, edition_type, generated_at, window_start, window_end, article_count)
    VALUES
        (v_edition_name, p_edition_type, NOW(), v_window_start, NOW(), 0);

    SET v_newsletter_id = LAST_INSERT_ID();

    -- insert matching articles ranked by importance_score
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

    -- update the count
    UPDATE newsletter_editions
    SET article_count = (
        SELECT COUNT(*) FROM newsletter_articles
        WHERE newsletter_id = v_newsletter_id
    )
    WHERE id = v_newsletter_id;

    SELECT v_newsletter_id AS newsletter_id;
END$$
DELIMITER ;


-- extra indexes for the stored procedure queries
CREATE INDEX IF NOT EXISTS idx_articles_published_at   ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_article_tags_tag_id     ON article_tags(tag_id);
CREATE INDEX IF NOT EXISTS idx_article_tags_article_id ON article_tags(article_id);
CREATE INDEX IF NOT EXISTS idx_articles_source_id      ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_ingested_at    ON articles(ingested_at);
CREATE INDEX IF NOT EXISTS idx_articles_importance     ON articles(importance_score);
