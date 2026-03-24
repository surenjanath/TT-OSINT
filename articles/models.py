from django.db import models


class NewsSource(models.Model):
    """A news source to scrape articles from."""
    SCRAPER_TYPES = [
        ('rss', 'RSS Feed'),
        ('web', 'Web Scraper'),
        ('api', 'JSON API'),
    ]

    name = models.CharField(max_length=200)
    url = models.URLField(help_text="Main site URL")
    rss_url = models.URLField(blank=True, null=True, help_text="RSS feed URL or API Endpoint URL")
    scraper_type = models.CharField(max_length=10, choices=SCRAPER_TYPES, default='rss')
    
    # API configuration fields
    api_headers = models.JSONField(
        blank=True, null=True, 
        help_text="JSON dictionary of headers to send with the request"
    )
    api_mapping = models.JSONField(
        blank=True, null=True,
        help_text='''JSON dictionary mapping response fields. 
        Example: {"items_path": "rows", "title_field": "title", "url_field": "url", "content_field": "presentation", "author_field": "author", "date_field": "published_date"}'''
    )
    
    max_articles_per_scrape = models.IntegerField(
        blank=True, null=True,
        help_text="Override the global max articles limit for this specific source"
    )
    api_pagination = models.JSONField(
        blank=True, null=True,
        help_text='JSON pagination config. Example: {"enabled": true, "param": "o", "page_size": 100, "max_pages": 5}'
    )
    api_date_range = models.JSONField(
        blank=True, null=True,
        help_text='Date range params. Example: {"start_param": "d1", "end_param": "d2", "format": "%Y-%m-%d"}'
    )

    is_active = models.BooleanField(default=True)
    last_checked = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Scraping progress tracking
    oldest_article_date = models.DateTimeField(
        blank=True, null=True,
        help_text="Oldest article publication date scraped from this source"
    )
    newest_article_date = models.DateTimeField(
        blank=True, null=True,
        help_text="Newest article publication date scraped from this source"
    )
    total_articles_scraped = models.IntegerField(
        default=0,
        help_text="Running count of articles successfully scraped"
    )
    historical_complete = models.BooleanField(
        default=False,
        help_text="Whether the initial historical backfill has been completed"
    )

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['is_active', 'name']),
        ]

    def __str__(self):
        return self.name


class Article(models.Model):
    """A scraped news article."""
    title = models.CharField(max_length=500)
    content = models.TextField(blank=True, default='')
    url = models.URLField(unique=True, max_length=1000)
    source = models.ForeignKey(
        NewsSource, on_delete=models.CASCADE, related_name='articles'
    )
    author = models.CharField(max_length=200, blank=True, default='')
    published_date = models.DateTimeField(blank=True, null=True)
    scraped_date = models.DateTimeField(auto_now_add=True)
    is_processed = models.BooleanField(
        default=False,
        help_text="Whether the AI extraction pipeline has processed this article successfully"
    )
    processing_error = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Last error message if AI extraction was attempted and failed (e.g. timeout, connection)."
    )
    tags = models.CharField(max_length=500, blank=True, default='')
    image_url = models.URLField(max_length=1000, blank=True, null=True)
    summary = models.TextField(blank=True, default='')
    raw_api_data = models.JSONField(
        blank=True,
        null=True,
        help_text="Raw JSON object from the API for this article (API sources only)."
    )

    class Meta:
        ordering = ['-published_date']
        indexes = [
            models.Index(fields=['is_processed']),
            models.Index(fields=['published_date']),
            models.Index(fields=['source', 'published_date']),
        ]

    def __str__(self):
        return self.title

    @property
    def tags_list(self):
        """Return list of non-empty tags from comma-separated tags string."""
        if not self.tags:
            return []
        return [t.strip() for t in self.tags.split(',') if t.strip()]


class Story(models.Model):
    """A cluster of articles covering the same event/story across sources and days."""
    title = models.CharField(max_length=500)
    summary = models.TextField(blank=True, default='')
    articles = models.ManyToManyField(Article, related_name='stories', blank=True)
    primary_incident = models.ForeignKey(
        'incidents.Incident',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='stories',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name_plural = 'Stories'

    def __str__(self):
        return self.title


class ScrapeJob(models.Model):
    """Tracks each scrape run for auditing and debugging."""
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    source = models.ForeignKey(NewsSource, on_delete=models.CASCADE, related_name='scrape_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    date_from = models.DateField(blank=True, null=True)
    date_to = models.DateField(blank=True, null=True)
    articles_found = models.IntegerField(default=0)
    articles_new = models.IntegerField(default=0)
    articles_skipped = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    pages_fetched = models.IntegerField(default=0)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"{self.source.name} {self.started_at:%Y-%m-%d %H:%M} [{self.status}]"

    @property
    def elapsed(self):
        if self.finished_at and self.started_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
