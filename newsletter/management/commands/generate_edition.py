"""
python manage.py generate_edition --type ai_only [--render]

Generates a newsletter edition by calling the MySQL stored procedure,
then optionally prints the rendered HTML to stdout.
"""
from django.core.management.base import BaseCommand
from newsletter.pipeline.newsletter import (
    generate_edition, render_edition, VALID_EDITION_TYPES, EDITION_LABELS,
)


class Command(BaseCommand):
    help = 'Generate a newsletter edition via the newsletter_generate stored procedure'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            required=True,
            choices=VALID_EDITION_TYPES,
            metavar='EDITION_TYPE',
            help=f'Edition type: {", ".join(VALID_EDITION_TYPES)}',
        )
        parser.add_argument(
            '--render',
            action='store_true',
            help='Print the rendered edition HTML to stdout',
        )

    def handle(self, *args, **options):
        edition_type = options['type']
        label = EDITION_LABELS[edition_type]

        self.stdout.write(f'Generating "{label}" edition…')

        try:
            edition = generate_edition(edition_type)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Failed: {exc}'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'Edition created: "{edition.name}" '
            f'(id={edition.pk}, articles={edition.article_count})'
        ))

        if options['render']:
            self.stdout.write('\n' + '─' * 60)
            self.stdout.write(render_edition(edition))
