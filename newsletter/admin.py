from django.contrib import admin
from django.utils.html import format_html
from .models import Source, Article, Tag, TagRule, ArticleTag, NewsletterEdition, NewsletterArticle


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'base_url', 'reliability_score', 'article_count', 'created_at']
    search_fields = ['name', 'base_url']
    ordering = ['name']

    def article_count(self, obj):
        return obj.articles.count()
    article_count.short_description = 'Articles'


class TagRuleInline(admin.TabularInline):
    model = TagRule
    extra = 1
    fields = ['keyword', 'match_field', 'priority']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['tag_name', 'tag_type', 'usage_count', 'rule_count']
    list_filter = ['tag_type']
    search_fields = ['tag_name', 'description']
    inlines = [TagRuleInline]

    def rule_count(self, obj):
        return obj.rules.count()
    rule_count.short_description = 'Rules'


@admin.register(TagRule)
class TagRuleAdmin(admin.ModelAdmin):
    list_display = ['keyword', 'tag', 'match_field', 'priority']
    list_filter = ['match_field', 'tag__tag_type']
    search_fields = ['keyword', 'tag__tag_name']
    ordering = ['-priority', 'keyword']


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title_short', 'source', 'tagging_method', 'importance_score', 'tag_list', 'published_at', 'ingested_at']
    list_filter = ['tagging_method', 'source', 'published_at']
    search_fields = ['title', 'content', 'url']
    readonly_fields = ['ingested_at', 'url_link']
    date_hierarchy = 'ingested_at'
    ordering = ['-ingested_at']

    def title_short(self, obj):
        return obj.title[:70] + ('…' if len(obj.title) > 70 else '')
    title_short.short_description = 'Title'

    def url_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.url, obj.url)
    url_link.short_description = 'URL'

    def tag_list(self, obj):
        tags = obj.article_tags.select_related('tag').all()
        return ', '.join(at.tag.tag_name for at in tags[:5])
    tag_list.short_description = 'Tags'


@admin.register(ArticleTag)
class ArticleTagAdmin(admin.ModelAdmin):
    list_display = ['article_title', 'tag', 'confidence', 'assigned_by', 'tagged_at']
    list_filter = ['assigned_by', 'tag__tag_type', 'tag']
    search_fields = ['article__title', 'tag__tag_name']
    date_hierarchy = 'tagged_at'

    def article_title(self, obj):
        return obj.article.title[:60]
    article_title.short_description = 'Article'


class NewsletterArticleInline(admin.TabularInline):
    model = NewsletterArticle
    extra = 0
    fields = ['position', 'article', 'section_summary']
    readonly_fields = ['position', 'article']
    ordering = ['position']


@admin.register(NewsletterEdition)
class NewsletterEditionAdmin(admin.ModelAdmin):
    list_display = ['name', 'edition_type', 'article_count', 'window_start', 'window_end', 'generated_at']
    list_filter = ['edition_type']
    readonly_fields = ['generated_at', 'article_count']
    date_hierarchy = 'generated_at'
    inlines = [NewsletterArticleInline]


@admin.register(NewsletterArticle)
class NewsletterArticleAdmin(admin.ModelAdmin):
    list_display = ['newsletter', 'position', 'article_title']
    list_filter = ['newsletter__edition_type']
    ordering = ['newsletter', 'position']

    def article_title(self, obj):
        return obj.article.title[:60]
    article_title.short_description = 'Article'
