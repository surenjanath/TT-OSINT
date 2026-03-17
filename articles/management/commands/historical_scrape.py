"""
Management command: Deep historical scrape to backfill articles from 2020 to current.
For API sources: paginates deeply through all available articles.
For RSS sources: paginates through ?paged=N until exhausted.
Tracks progress and marks sources as historical_complete when done.

Usage:
  python manage.py historical_scrape                    # All active sources
  python manage.py historical_scrape --source "Trinidad Express (API)"
  python manage.py historical_scrape --max-pages 200    # Override max pages
  python manage.py historical_scrape --since 2022-01-01 # Override start date
"""
import sys
import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from articles.models import NewsSource, Article
from articles.services import (
    RSSFeedParser, APIScraper, WebScraper, ArticleIngestionService,
    normalize_url,
)
from core.models import SystemSetting


class Command(BaseCommand):
    help = 'Deep historical scrape: backfill articles from 2020 to present'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    def add_arguments(self, parser):
        parser.add_argument('--source', type=str, help='Scrape only this source (by name)')
        parser.add_argument('--max-pages', type=int, default=0, help='Max pages to fetch (0=unlimited)')
        parser.add_argument('--since', type=str, default='2020-01-01', help='Scrape articles from this date (YYYY-MM-DD)')
        parser.add_argument('--reset', action='store_true', help='Reset historical_complete flag and re-scrape')

    def handle(self, *args, **options):
        source_name = options.get('source')
        max_pages_override = options['max_pages']
        since_str = options['since']
        reset = options['reset']

        # Pull defaults from SystemSettings if not overridden on CLI
        if since_str == '2020-01-01':
            try:
                db_since = SystemSetting.get_setting('historical_date_from', '2020-01-01')
                if db_since:
                    since_str = db_since
            except Exception:
                pass
        if max_pages_override == 0:
            try:
                db_pages = int(SystemSetting.get_setting('historical_max_pages', '0'))
                max_pages_override = db_pages
            except Exception:
                pass

        try:
            since_date = timezone.make_aware(datetime.strptime(since_str, '%Y-%m-%d'))
        except ValueError:
            self.stderr.write(f'Invalid date format: {since_str}. Use YYYY-MM-DD.')
            return

        if source_name:
            sources = list(NewsSource.objects.filter(name=source_name, is_active=True))
            if not sources:
                self.stderr.write(f'No active source found with name: {source_name}')
                return
        else:
            sources = list(NewsSource.objects.filter(is_active=True))

        if reset:
            for s in sources:
                s.historical_complete = False
                s.save(update_fields=['historical_complete'])

        try:
            scraper_timeout = int(SystemSetting.get_setting('scraper_timeout', '15'))
        except Exception:
            scraper_timeout = 15

        rss_parser = RSSFeedParser()
        api_scraper = APIScraper()
        web_scraper = WebScraper()
        ingestion = ArticleIngestionService(log_fn=self._log)

        total_new = 0
        pipeline_start = time.time()

        self._log(f'Starting historical scrape from {since_str} for {len(sources)} source(s)', 'info')

        for source in sources:
            if source.historical_complete and not reset:
                self._log(f'  Skipping {source.name} (historical_complete=True, use --reset to re-scrape)', 'info')
                continue

            source_start = time.time()
            self._log(f'\n=== {source.name} ({source.scraper_type.upper()}) ===', 'info')

            if source.scraper_type == 'api':
                new_count = self._historical_api(source, api_scraper, web_scraper, scraper_timeout, since_date, max_pages_override)
            elif source.scraper_type == 'rss':
                new_count = self._historical_rss(source, rss_parser, web_scraper, scraper_timeout, since_date, max_pages_override)
            else:
                self._log(f'  Web scraper does not support historical pagination -- skipping', 'warning')
                new_count = 0

            total_new += new_count
            source.historical_complete = True
            source.last_checked = timezone.now()
            source.save(update_fields=[
                'last_checked', 'historical_complete',
                'oldest_article_date', 'newest_article_date', 'total_articles_scraped',
            ])
            elapsed = time.time() - source_start
            self._log(f'  Done: {source.name} +{new_count} new articles ({elapsed:.1f}s)', 'success')

        total_elapsed = time.time() - pipeline_start
        self._log(f'\nHistorical scrape complete: {total_new} total new articles in {total_elapsed:.1f}s', 'success')

    def _historical_api(self, source, api_scraper, web_scraper, timeout, since_date, max_pages_override):
        """Deep paginate through API source."""
        original_pagination = source.api_pagination or {}
        deep_pagination = dict(original_pagination)
        deep_pagination['enabled'] = True
        if max_pages_override:
            deep_pagination['max_pages'] = max_pages_override
        else:
            deep_pagination['max_pages'] = 0  # unlimited (up to safety limit)

        source.api_pagination = deep_pagination
        raw_articles = api_scraper.fetch_articles(source, log_fn=self._log, timeout=timeout)
        source.api_pagination = original_pagination

        return self._save_articles(source, raw_articles, web_scraper, timeout, since_date)

    def _historical_rss(self, source, rss_parser, web_scraper, timeout, since_date, max_pages_override):
        """Deep paginate through RSS feed pages."""
        original_pagination = source.api_pagination or {}
        deep_pagination = dict(original_pagination)
        deep_pagination['enabled'] = True
        if max_pages_override:
            deep_pagination['max_pages'] = max_pages_override
        else:
            deep_pagination['max_pages'] = 0  # unlimited (up to safety limit)

        source.api_pagination = deep_pagination
        raw_articles = rss_parser.fetch_articles(source, log_fn=self._log)
        source.api_pagination = original_pagination

        return self._save_articles(source, raw_articles, web_scraper, timeout, since_date)

    def _save_articles(self, source, raw_articles, web_scraper, timeout, since_date):
        """Save articles, filtering by date and skipping duplicates."""
        new_count = 0
        skipped = 0

        for raw in raw_articles:
            if not raw.get('url'):
                continue

            pub_date = raw.get('published_date')
            if pub_date and pub_date < since_date:
                continue

            if Article.objects.filter(url=raw['url']).exists():
                skipped += 1
                continue
            normalized = normalize_url(raw['url'])
            if normalized != raw['url'] and Article.objects.filter(url=normalized).exists():
                skipped += 1
                continue

            content = raw.get('content', '')
            if len(content) < 100 and raw['url']:
                try:
                    content, scraped_date = web_scraper.fetch_article_content(raw['url'], timeout=timeout)
                    if scraped_date and not pub_date:
                        raw['published_date'] = scraped_date
                        pub_date = scraped_date
                except Exception:
                    pass

            try:
                Article.objects.create(
                    title=raw['title'][:500],
                    content=content,
                    url=raw['url'],
                    source=source,
                    author=raw.get('author', '')[:200],
                    published_date=pub_date,
                    tags=raw.get('tags', '')[:500],
                    image_url=raw.get('image_url') or None,
                    summary=(raw.get('summary') or '')[:2000],
                )
                new_count += 1
                ArticleIngestionService._update_source_tracking(source, pub_date, 1)
            except Exception as e:
                self._log(f'    Failed to save: {e}', 'error')

        self._log(f'  Saved {new_count} new, {skipped} duplicates skipped', 'info')
        return new_count

    def _log(self, msg, level='info'):
        self.stdout.write(msg)
