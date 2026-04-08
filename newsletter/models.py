from django.db import models


class Source(models.Model):
    name = models.CharField(max_length=255)
    base_url = models.CharField(max_length=500)
    reliability_score = models.FloatField(default=1.0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sources'
        ordering = ['name']

    def __str__(self):
        return self.name


class Article(models.Model):
    TAGGING_CHOICES = [('llm', 'LLM'), ('rules', 'Rules'), ('none', 'None')]

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name='articles')
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True)
    content = models.TextField()
    url = models.CharField(max_length=255, unique=True)
    tagging_method = models.CharField(max_length=10, choices=TAGGING_CHOICES, default='none')
    importance_score = models.FloatField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    ingested_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'articles'
        ordering = ['-ingested_at']
        indexes = [
            models.Index(fields=['published_at']),
            models.Index(fields=['source']),
            models.Index(fields=['tagging_method']),
        ]

    def __str__(self):
        return self.title[:80]


class Tag(models.Model):
    TAG_TYPE_CHOICES = [
        ('topic', 'Topic'),
        ('geography', 'Geography'),
        ('article_type', 'Article Type'),
    ]

    tag_name = models.CharField(max_length=100, unique=True)
    tag_type = models.CharField(max_length=20, choices=TAG_TYPE_CHOICES)
    description = models.CharField(max_length=500, blank=True)
    usage_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'tags'
        ordering = ['tag_type', 'tag_name']

    def __str__(self):
        return f'{self.tag_name} ({self.tag_type})'


class TagRule(models.Model):
    MATCH_FIELD_CHOICES = [('title', 'Title'), ('content', 'Content')]

    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='rules')
    keyword = models.CharField(max_length=200)
    match_field = models.CharField(max_length=10, choices=MATCH_FIELD_CHOICES)
    priority = models.IntegerField(default=1)

    class Meta:
        db_table = 'tag_rules'
        ordering = ['-priority', 'keyword']

    def __str__(self):
        return f'{self.keyword} → {self.tag.tag_name} (in {self.match_field})'


class ArticleTag(models.Model):
    ASSIGNED_BY_CHOICES = [('llm', 'LLM'), ('rules', 'Rules')]

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='article_tags')
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name='article_tags')
    confidence = models.FloatField()
    assigned_by = models.CharField(max_length=10, choices=ASSIGNED_BY_CHOICES)
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'article_tags'
        unique_together = [('article', 'tag')]
        indexes = [
            models.Index(fields=['tag']),
            models.Index(fields=['article']),
            models.Index(fields=['assigned_by']),
        ]

    def __str__(self):
        return f'{self.article.title[:40]} → {self.tag.tag_name} ({self.confidence:.2f})'


class NewsletterEdition(models.Model):
    EDITION_CHOICES = [
        ('general', 'General Tech'),
        ('ai_only', 'AI Only'),
        ('startups', 'Startups & VC'),
        ('policy', 'Policy & Reg.'),
        ('europe', 'Europe Focus'),
    ]

    name = models.CharField(max_length=255)
    edition_type = models.CharField(max_length=20, choices=EDITION_CHOICES)
    generated_at = models.DateTimeField(auto_now_add=True)
    window_start = models.DateTimeField()
    window_end = models.DateTimeField()
    article_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'newsletter_editions'
        ordering = ['-generated_at']

    def __str__(self):
        return self.name


class NewsletterArticle(models.Model):
    newsletter = models.ForeignKey(
        NewsletterEdition, on_delete=models.CASCADE, related_name='newsletter_articles'
    )
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='newsletter_articles')
    position = models.IntegerField()
    section_summary = models.TextField(blank=True)

    class Meta:
        db_table = 'newsletter_articles'
        unique_together = [('newsletter', 'article')]
        ordering = ['position']

    def __str__(self):
        return f'Edition {self.newsletter_id} — pos {self.position}: {self.article.title[:40]}'
