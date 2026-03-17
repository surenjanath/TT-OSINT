"""
Management command: Cluster articles into stories by heuristic matching.
Usage: python manage.py cluster_stories [--days 14] [--overlap 0.4] [--limit 5000]
"""
import sys

from django.core.management.base import BaseCommand
from articles.clustering import cluster_stories


class Command(BaseCommand):
    help = 'Group articles into story clusters by title overlap and shared incident category'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=14,
            help='Date window (days each side) for matching articles (default: 14)',
        )
        parser.add_argument(
            '--overlap',
            type=float,
            default=0.4,
            help='Minimum title word overlap ratio 0-1 (default: 0.4)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Max number of articles to consider (default: all in window)',
        )

    def handle(self, *args, **options):
        def log_fn(msg, level='info'):
            self.stdout.write(msg)

        n = cluster_stories(
            window_days=options['days'],
            min_overlap=options['overlap'],
            limit=options['limit'],
            log_fn=log_fn,
        )
        self.stdout.write(self.style.SUCCESS(f'Done. {n} article(s) assigned to stories.'))
