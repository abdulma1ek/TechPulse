"""
python manage.py seed_tags

Seeds the Tag and TagRule tables with the controlled vocabulary
and keyword rules defined in the project brief.
"""
from django.core.management.base import BaseCommand
from newsletter.models import Tag, TagRule


TAGS = [
    # Topics
    ('ai', 'topic', 'Artificial intelligence, machine learning, LLMs'),
    ('hardware', 'topic', 'Chips, devices, physical computing products'),
    ('software', 'topic', 'Applications, platforms, operating systems'),
    ('security', 'topic', 'Cybersecurity, data breaches, privacy'),
    ('policy', 'topic', 'Tech regulation, government, legislation'),
    ('startup', 'topic', 'Startups, new companies, early-stage ventures'),
    ('funding', 'topic', 'VC funding, investment rounds, IPOs'),
    ('acquisition', 'topic', 'M&A, acquisitions, mergers'),
    # Geography
    ('us', 'geography', 'United States'),
    ('europe', 'geography', 'European Union and European countries'),
    ('china', 'geography', 'China, Chinese tech companies'),
    ('global', 'geography', 'Global, worldwide, international'),
    # Article types
    ('product-launch', 'article_type', 'Product announcements and launches'),
    ('research', 'article_type', 'Research papers, studies, findings'),
    ('analysis', 'article_type', 'Opinion, analysis, in-depth commentary'),
    ('funding-round', 'article_type', 'Funding announcements, investment rounds'),
    ('regulation', 'article_type', 'Regulatory decisions, government actions'),
]

# (tag_name, keyword, match_field, priority)
TAG_RULES = [
    # ai
    ('ai', 'artificial intelligence', 'title', 10),
    ('ai', 'artificial intelligence', 'content', 5),
    ('ai', 'machine learning', 'title', 10),
    ('ai', 'machine learning', 'content', 5),
    ('ai', 'deep learning', 'title', 10),
    ('ai', 'deep learning', 'content', 5),
    ('ai', 'large language model', 'content', 5),
    ('ai', 'llm', 'title', 8),
    ('ai', 'chatgpt', 'title', 9),
    ('ai', 'chatgpt', 'content', 4),
    ('ai', 'openai', 'title', 9),
    ('ai', 'openai', 'content', 4),
    ('ai', 'claude', 'title', 9),
    ('ai', 'gemini', 'title', 8),
    ('ai', 'gpt-4', 'content', 5),
    # hardware
    ('hardware', 'chip', 'title', 8),
    ('hardware', 'semiconductor', 'title', 9),
    ('hardware', 'processor', 'title', 8),
    ('hardware', 'nvidia', 'title', 8),
    ('hardware', 'intel', 'title', 8),
    ('hardware', 'amd', 'title', 8),
    ('hardware', 'apple silicon', 'title', 9),
    ('hardware', 'gpu', 'title', 8),
    ('hardware', 'datacenter', 'content', 4),
    # software
    ('software', 'app', 'title', 6),
    ('software', 'platform', 'title', 6),
    ('software', 'software update', 'title', 8),
    ('software', 'open source', 'title', 8),
    ('software', 'developer', 'content', 3),
    ('software', 'api', 'title', 7),
    # security
    ('security', 'hack', 'title', 9),
    ('security', 'breach', 'title', 10),
    ('security', 'vulnerability', 'title', 10),
    ('security', 'ransomware', 'title', 10),
    ('security', 'cybersecurity', 'title', 10),
    ('security', 'privacy', 'title', 8),
    ('security', 'data leak', 'title', 10),
    # policy
    ('policy', 'regulation', 'title', 9),
    ('policy', 'congress', 'title', 8),
    ('policy', 'senate', 'title', 7),
    ('policy', 'antitrust', 'title', 10),
    ('policy', 'ban', 'title', 7),
    ('policy', 'law', 'title', 6),
    ('policy', 'ftc', 'title', 9),
    ('policy', 'doj', 'title', 9),
    # startup
    ('startup', 'startup', 'title', 10),
    ('startup', 'founded', 'content', 4),
    ('startup', 'seed round', 'title', 9),
    ('startup', 'series a', 'title', 9),
    ('startup', 'series b', 'title', 9),
    ('startup', 'venture', 'content', 4),
    # funding
    ('funding', 'raises', 'title', 9),
    ('funding', 'funding', 'title', 9),
    ('funding', 'investment', 'title', 8),
    ('funding', 'ipo', 'title', 10),
    ('funding', 'valuation', 'title', 8),
    ('funding', 'billion', 'title', 6),
    ('funding', 'million', 'title', 5),
    # acquisition
    ('acquisition', 'acquires', 'title', 10),
    ('acquisition', 'acquisition', 'title', 10),
    ('acquisition', 'merger', 'title', 10),
    ('acquisition', 'buys', 'title', 9),
    ('acquisition', 'deal', 'title', 6),
    # geography
    ('us', 'united states', 'content', 4),
    ('us', 'silicon valley', 'content', 5),
    ('us', 'white house', 'content', 5),
    ('europe', 'european union', 'content', 5),
    ('europe', 'eu ', 'content', 4),
    ('europe', 'gdpr', 'title', 9),
    ('europe', 'brussels', 'content', 5),
    ('china', 'china', 'title', 8),
    ('china', 'chinese', 'title', 7),
    ('china', 'beijing', 'content', 5),
    ('china', 'huawei', 'title', 8),
    ('china', 'tiktok', 'title', 8),
    # article types
    ('product-launch', 'launches', 'title', 9),
    ('product-launch', 'introduces', 'title', 8),
    ('product-launch', 'unveils', 'title', 9),
    ('product-launch', 'announces', 'title', 7),
    ('research', 'study', 'title', 8),
    ('research', 'researchers', 'title', 8),
    ('research', 'paper', 'title', 7),
    ('research', 'report', 'title', 6),
    ('funding-round', 'series a', 'title', 10),
    ('funding-round', 'series b', 'title', 10),
    ('funding-round', 'series c', 'title', 10),
    ('funding-round', 'seed round', 'title', 10),
    ('regulation', 'ftc', 'title', 10),
    ('regulation', 'sec', 'title', 9),
    ('regulation', 'fines', 'title', 9),
    ('regulation', 'eu ai act', 'title', 10),
]


class Command(BaseCommand):
    help = 'Seed Tag and TagRule tables with the TechPulse controlled vocabulary'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing tags and rules before seeding',
        )

    def handle(self, *args, **options):
        if options['clear']:
            TagRule.objects.all().delete()
            Tag.objects.all().delete()
            self.stdout.write('Cleared existing tags and rules.')

        tags_created = 0
        tags_skipped = 0
        for tag_name, tag_type, description in TAGS:
            _, created = Tag.objects.get_or_create(
                tag_name=tag_name,
                defaults={'tag_type': tag_type, 'description': description},
            )
            if created:
                tags_created += 1
            else:
                tags_skipped += 1

        rules_created = 0
        rules_skipped = 0
        for tag_name, keyword, match_field, priority in TAG_RULES:
            try:
                tag = Tag.objects.get(tag_name=tag_name)
            except Tag.DoesNotExist:
                self.stderr.write(f'Tag not found: {tag_name}')
                continue
            _, created = TagRule.objects.get_or_create(
                tag=tag,
                keyword=keyword,
                match_field=match_field,
                defaults={'priority': priority},
            )
            if created:
                rules_created += 1
            else:
                rules_skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'Tags: {tags_created} created, {tags_skipped} already existed\n'
            f'Rules: {rules_created} created, {rules_skipped} already existed'
        ))
