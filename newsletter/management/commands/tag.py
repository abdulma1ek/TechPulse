"""
python manage.py tag [--limit 50] [--method auto|llm|rules]

Runs the tagging pipeline on untagged articles.
Primary: Claude LLM. Fallback: keyword rules from tag_rules table.
"""
from django.core.management.base import BaseCommand
from newsletter.pipeline.tagger import run_tagger


class Command(BaseCommand):
    help = 'Tag untagged articles using Claude LLM (primary) and keyword rules (fallback)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=50,
            help='Maximum number of articles to tag per run (default: 50)',
        )
        parser.add_argument(
            '--method',
            type=str,
            default='auto',
            choices=['auto', 'llm', 'rules'],
            help='Tagging method: auto (LLM + fallback), llm, or rules (default: auto)',
        )

    def handle(self, *args, **options):
        limit = options['limit']
        method = options['method']

        self.stdout.write(f'Tagging up to {limit} articles (method={method})…')
        result = run_tagger(limit=limit, method=method)

        self.stdout.write(self.style.SUCCESS(
            f"Processed {result['processed']} article(s): "
            f"{result['llm_tagged']} LLM, "
            f"{result['rules_tagged']} rules, "
            f"{result['untagged']} untagged"
        ))
