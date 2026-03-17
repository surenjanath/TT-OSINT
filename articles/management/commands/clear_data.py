"""
Management command: Clear all articles, incidents, and source timestamps for a fresh start.
Usage: python manage.py clear_data
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Clear all articles, incidents, and reset source timestamps'

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='Skip confirmation prompt')

    def handle(self, *args, **options):
        from articles.models import Article, NewsSource
        from incidents.models import Incident

        if not options['yes']:
            confirm = input('This will DELETE all articles and incidents. Continue? [y/N] ')
            if confirm.lower() not in ('y', 'yes'):
                self.stdout.write('Aborted.')
                return

        inc_count = Incident.objects.count()
        art_count = Article.objects.count()

        Incident.objects.all().delete()
        self.stdout.write(f'  Deleted {inc_count} incidents')

        Article.objects.all().delete()
        self.stdout.write(f'  Deleted {art_count} articles')

        NewsSource.objects.all().update(last_checked=None)
        self.stdout.write(f'  Reset last_checked on all sources')

        self.stdout.write(self.style.SUCCESS('Done. Database is clean for re-test.'))
