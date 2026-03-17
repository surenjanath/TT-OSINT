"""
Management command: Process unprocessed articles through AI extraction.
Usage: python manage.py process_articles [--limit N]
Limit defaults to the "Process Limit" value in Settings > AI Extractor Settings.
"""
from django.core.management.base import BaseCommand
from core.models import SystemSetting
from incidents.services import IncidentProcessorService


class Command(BaseCommand):
    help = 'Process unprocessed articles through AI extraction and geocoding'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit', type=int, default=None,
            help='Max articles to process (overrides Settings > AI Extractor limit)'
        )

    def handle(self, *args, **options):
        limit = options.get('limit')
        if limit is None:
            limit = int(SystemSetting.get_setting('ai_extractor_limit', '1000'))
        limit = max(1, min(5000, limit))
        self.stdout.write(self.style.NOTICE(
            f'Processing up to {limit} unprocessed articles...'
        ))

        def log_fn(msg, level='info'):
            try:
                self.stdout.write(msg)
            except UnicodeEncodeError:
                self.stdout.write(msg.encode('ascii', 'replace').decode())

        service = IncidentProcessorService(log_fn=log_fn)
        count = service.process_unprocessed_articles(limit=limit)

        self.stdout.write(
            self.style.SUCCESS(f'Done. {count} incidents extracted.')
        )
