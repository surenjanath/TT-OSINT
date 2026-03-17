"""
Management command: Seed initial news sources for Trinidad & Tobago.
Usage: python manage.py seed_sources
"""
from django.core.management.base import BaseCommand
from articles.models import NewsSource


# Trinidad Express BLOX/TownNews API mapping
TRINIDAD_EXPRESS_API_MAPPING = {
    'items_path': 'rows',
    'title_field': 'title',
    'url_field': 'url',
    'content_field': 'content',
    'author_field': 'byline',
    'date_field': 'starttime.iso8601',
    'tags_field': 'sections',
    'image_field': 'preview.url',
    'summary_field': 'prologue',
}

TRINIDAD_EXPRESS_API_PAGINATION = {
    'enabled': True,
    'type': 'offset',
    'param': 'o',
    'page_size': 25,
    'max_pages': 20,
}

RSS_PAGINATION = {
    'enabled': True,
    'max_pages': 10,
}


SOURCES = [
    {
        'name': 'CNC3',
        'url': 'https://www.cnc3.co.tt/',
        'rss_url': 'https://www.cnc3.co.tt/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Trinidad Newsday',
        'url': 'https://newsday.co.tt/',
        'rss_url': 'https://newsday.co.tt/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Trinidad Express (API)',
        'url': 'https://trinidadexpress.com/',
        'rss_url': 'https://trinidadexpress.com/search/?f=json&l=25&sd=desc&s=start_time&t=article',
        'scraper_type': 'api',
        'api_mapping': TRINIDAD_EXPRESS_API_MAPPING,
        'api_pagination': TRINIDAD_EXPRESS_API_PAGINATION,
    },
    {
        'name': 'Loop TT',
        'url': 'https://tt.loopnews.com/',
        'rss_url': 'https://tt.loopnews.com/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Guardian Media',
        'url': 'https://www.guardian.co.tt/',
        'rss_url': 'https://www.guardian.co.tt/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'TV6 TnT',
        'url': 'https://www.tv6tnt.com/',
        'rss_url': 'https://www.tv6tnt.com/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Power 102.1 FM',
        'url': 'https://power102fm.com/',
        'rss_url': 'https://power102fm.com/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'i95.5 FM',
        'url': 'https://i955fm.com/',
        'rss_url': 'https://i955fm.com/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'TTPS (Trinidad and Tobago Police Service)',
        'url': 'https://www.ttps.gov.tt/',
        'rss_url': 'https://www.ttps.gov.tt/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Wired868',
        'url': 'https://wired868.com/',
        'rss_url': 'https://wired868.com/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
    {
        'name': 'Trinidad and Tobago Guardian',
        'url': 'https://www.guardian.co.tt/',
        'rss_url': 'https://www.guardian.co.tt/news/feed/',
        'scraper_type': 'rss',
        'api_pagination': RSS_PAGINATION,
    },
]


class Command(BaseCommand):
    help = 'Seed the database with Trinidad & Tobago news sources'

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for src in SOURCES:
            name = src['name']
            obj, was_created = NewsSource.objects.get_or_create(
                name=name,
                defaults=src,
            )
            if was_created:
                created += 1
                self.stdout.write(f"  + {obj.name}")
            else:
                changed = False
                for field in ('url', 'rss_url', 'scraper_type', 'api_headers', 'api_mapping', 'api_pagination'):
                    new_val = src.get(field)
                    if new_val is not None and getattr(obj, field) != new_val:
                        setattr(obj, field, new_val)
                        changed = True
                if changed:
                    obj.save()
                    updated += 1
                    self.stdout.write(f"  * {obj.name} (updated)")
                else:
                    self.stdout.write(f"  ~ {obj.name} (already exists)")

        self.stdout.write(
            self.style.SUCCESS(f'Done. {created} new, {updated} updated.')
        )
