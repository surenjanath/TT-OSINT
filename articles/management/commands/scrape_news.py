"""
Management command: Scrape news articles from all active sources.
Usage: python manage.py scrape_news [--source "Name"]
"""
import sys

from django.core.management.base import BaseCommand
from articles.models import NewsSource
from articles.services import ArticleIngestionService


class Command(BaseCommand):
    help = 'Scrape news articles from all active RSS/web/API sources'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, help='Scrape only this source (by name)')

    def handle(self, *args, **options):
        source_name = options.get('source')

        def log_fn(msg, level='info'):
            self.stdout.write(msg)

        service = ArticleIngestionService(log_fn=log_fn)

        if source_name:
            try:
                source = NewsSource.objects.get(name=source_name, is_active=True)
            except NewsSource.DoesNotExist:
                self.stderr.write(f'No active source found: {source_name}')
                return
            count = service.ingest_source(source)
        else:
            count = service.ingest_all()

        self.stdout.write(self.style.SUCCESS(f'Done. {count} new articles ingested.'))
