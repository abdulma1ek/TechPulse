"""
python manage.py scrape [--source 1,2,3]

Scrapes RSS feeds from TechPulse sources and persists new articles.
"""
from django.core.management.base import BaseCommand
from newsletter.pipeline.scraper import run_scraper


class Command(BaseCommand):
    help = 'Scrape articles from RSS feeds (TechCrunch, The Verge, Ars Technica, Reuters Tech)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source',
            type=str,
            default=None,
            help='Comma-separated source IDs to scrape (default: all)',
        )

    def handle(self, *args, **options):
        source_ids = None
        if options['source']:
            try:
                source_ids = [int(x.strip()) for x in options['source'].split(',')]
            except ValueError:
                self.stderr.write('--source must be comma-separated integers, e.g. --source 1,2')
                return

        self.stdout.write('Starting scrape…')
        result = run_scraper(source_ids=source_ids)

        self.stdout.write(self.style.SUCCESS(
            f"Scraped {result['sources_scraped']} source(s): "
            f"{result['total_found']} articles found, "
            f"{result['total_new']} new"
        ))
        for err in result['errors']:
            self.stderr.write(f'  ERROR: {err}')
