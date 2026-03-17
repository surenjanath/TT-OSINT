"""
Heuristic-based story clustering: group articles that cover the same event.
No embeddings required; uses title word overlap, shared incident categories, and date window.
"""
import re
from datetime import timedelta

from django.utils import timezone
from django.db.models import Q

from .models import Article, Story
from incidents.models import Incident


# Common stopwords to exclude from title overlap
STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
    'might', 'must', 'shall', 'can', 'need', 'dare', 'ought', 'used', 'it', 'its',
})


def _title_words(title: str) -> set:
    """Extract normalized words from title (lowercase, alphanumeric, no stopwords)."""
    if not title:
        return set()
    words = set(re.findall(r'[a-z0-9]+', title.lower()))
    return words - STOPWORDS


def _word_overlap_ratio(words1: set, words2: set) -> float:
    """Jaccard-like overlap: |intersection| / |union|."""
    if not words1 or not words2:
        return 0.0
    inter = len(words1 & words2)
    union = len(words1 | words2)
    return inter / union if union else 0.0


def _article_incident_categories(article: Article) -> set:
    """Return set of incident categories for this article (from primary or linked incidents)."""
    # Articles can be primary_article of incidents or in related_articles
    cats = set(
        Incident.objects.filter(primary_article=article)
        .values_list('category', flat=True)
    )
    cats |= set(
        Incident.objects.filter(related_articles=article)
        .values_list('category', flat=True)
    )
    return cats


def _find_matching_story(
    article: Article,
    title_words: set,
    article_categories: set,
    published_date,
    window_days: int = 7,
    min_overlap: float = 0.4,
) -> Story | None:
    """
    Find an existing story that contains an article matching this one.
    Match: same story has an article with title overlap >= min_overlap,
    shared incident category, and published within window_days.
    """
    if not published_date:
        return None
    date_lo = published_date - timedelta(days=window_days)
    date_hi = published_date + timedelta(days=window_days)

    # Stories that have at least one article in the date window
    stories = Story.objects.filter(
        articles__published_date__date__gte=date_lo.date(),
        articles__published_date__date__lte=date_hi.date(),
    ).prefetch_related('articles').distinct()

    for story in stories:
        for other in story.articles.all():
            if other.pk == article.pk:
                continue
            if not other.published_date:
                continue
            if abs((other.published_date - published_date).days) > window_days:
                continue
            other_words = _title_words(other.title)
            if _word_overlap_ratio(title_words, other_words) < min_overlap:
                continue
            other_cats = _article_incident_categories(other)
            if article_categories and other_cats and not (article_categories & other_cats):
                continue
            return story
    return None


def cluster_stories(
    window_days: int = 7,
    min_overlap: float = 0.4,
    limit: int | None = None,
    log_fn=None,
) -> int:
    """
    Group articles into stories by heuristic matching.
    Processes articles with published_date in the last (window_days * 2) days.
    Returns the number of stories created or updated.
    """
    since = timezone.now() - timedelta(days=window_days * 2)
    qs = Article.objects.filter(
        published_date__gte=since,
        published_date__isnull=False,
    ).order_by('published_date')
    if limit:
        qs = qs[:limit]
    articles = list(qs)
    if log_fn:
        log_fn(f'Clustering {len(articles)} articles (window={window_days}d, min_overlap={min_overlap})', 'info')

    created_or_updated = 0
    for article in articles:
        title_words = _title_words(article.title)
        article_cats = _article_incident_categories(article)

        # Already in a story?
        if article.stories.exists():
            continue

        match = _find_matching_story(
            article, title_words, article_cats, article.published_date,
            window_days=window_days, min_overlap=min_overlap,
        )
        if match:
            match.articles.add(article)
            created_or_updated += 1
            if log_fn:
                log_fn(f'  + Article #{article.pk} → Story "{match.title[:50]}..."', 'info')
        else:
            # New single-article story (so future matching articles can join)
            primary_incident = (
                Incident.objects.filter(primary_article=article).order_by('incident_date').first()
                or Incident.objects.filter(related_articles=article).order_by('incident_date').first()
            )
            story = Story.objects.create(
                title=article.title[:500],
                summary=article.summary[:2000] if article.summary else '',
                primary_incident=primary_incident,
            )
            story.articles.add(article)
            created_or_updated += 1
            if log_fn:
                log_fn(f'  New story "{story.title[:50]}..." (Article #{article.pk})', 'info')

    return created_or_updated
