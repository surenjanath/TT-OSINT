"""
Views for the Articles feed.
"""
import json
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Count, Q, prefetch_related_objects
from .models import Article, NewsSource


def article_list_view(request):
    """List view for scraped articles with filters, search, and pagination."""
    articles_list = (
        Article.objects
        .select_related('source')
        .annotate(incident_count=Count('incidents'))
    )

    search = request.GET.get('search', '').strip()
    source_id = request.GET.get('source', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    processed_filter = request.GET.get('processed', '')  # '', 'yes', 'no'
    has_incidents_filter = request.GET.get('has_incidents', '')  # '', 'yes', 'no'

    if search:
        articles_list = articles_list.filter(
            Q(title__icontains=search) | Q(content__icontains=search) | Q(summary__icontains=search)
        )
    if source_id:
        articles_list = articles_list.filter(source_id=source_id)
    if date_from:
        articles_list = articles_list.filter(published_date__date__gte=date_from)
    if date_to:
        articles_list = articles_list.filter(published_date__date__lte=date_to)
    if processed_filter == 'yes':
        articles_list = articles_list.filter(is_processed=True)
    elif processed_filter == 'no':
        articles_list = articles_list.filter(is_processed=False)
    if has_incidents_filter == 'yes':
        articles_list = articles_list.filter(incident_count__gt=0)
    elif has_incidents_filter == 'no':
        articles_list = articles_list.filter(incident_count=0)

    articles_list = articles_list.order_by('-published_date')

    list_stats = articles_list.aggregate(
        total_filtered=Count('pk', distinct=True),
        processed_count=Count('pk', filter=Q(is_processed=True), distinct=True),
    )
    total_filtered = list_stats['total_filtered']
    processed_count = list_stats['processed_count']
    processed_pct = round(processed_count / total_filtered * 100) if total_filtered else 0
    if has_incidents_filter == 'yes':
        with_incidents_count = total_filtered
    elif has_incidents_filter == 'no':
        with_incidents_count = 0
    else:
        with_incidents_count = articles_list.filter(incident_count__gt=0).aggregate(
            c=Count('pk', distinct=True)
        )['c']
    with_incidents_pct = round(with_incidents_count / total_filtered * 100) if total_filtered else 0
    by_source = list(
        articles_list.values('source__name')
        .annotate(count=Count('pk', distinct=True))
        .order_by('-count')[:10]
    )

    paginator = Paginator(articles_list, 20)
    page_number = request.GET.get('paged', 1)
    page_obj = paginator.get_page(page_number)
    prefetch_related_objects(list(page_obj.object_list), 'incidents')

    context = {
        'page_title': 'News Feed',
        'page_obj': page_obj,
        'sources': NewsSource.objects.filter(is_active=True).order_by('name'),
        'total_filtered': total_filtered,
        'processed_count': processed_count,
        'processed_pct': processed_pct,
        'by_source': by_source,
        'with_incidents_count': with_incidents_count,
        'with_incidents_pct': with_incidents_pct,
        'filters': {
            'search': search,
            'source': source_id,
            'date_from': date_from,
            'date_to': date_to,
            'processed': processed_filter,
            'has_incidents': has_incidents_filter,
        },
    }
    return render(request, 'core/article_list.html', context)

def article_detail_view(request, pk):
    """Detail view for a specific article."""
    article = get_object_or_404(Article.objects.prefetch_related('stories'), pk=pk)
    incidents = article.incidents.all()
    word_count = len(article.content.split()) if article.content else 0

    raw_api_data_json = ''
    raw_api_rows = []
    if article.raw_api_data:
        try:
            raw_api_data_json = json.dumps(article.raw_api_data, indent=2, default=str)
        except Exception:
            raw_api_data_json = str(article.raw_api_data)
        for k, v in article.raw_api_data.items():
            if isinstance(v, (dict, list)):
                try:
                    display = json.dumps(v, indent=2, default=str)
                    if len(display) > 500:
                        display = display[:500] + '...'
                except Exception:
                    display = str(v)[:500]
            else:
                display = v if v is not None else '—'
            raw_api_rows.append((k, display))

    context = {
        'page_title': article.title,
        'article': article,
        'incidents': incidents,
        'word_count': word_count,
        'raw_api_data_json': raw_api_data_json,
        'raw_api_rows': raw_api_rows,
    }
    return render(request, 'core/article_detail.html', context)


def article_extraction_detail_view(request, pk):
    """Detail view showing article content and full AI extraction details for verification."""
    article = get_object_or_404(Article, pk=pk)
    incidents = list(article.incidents.all().order_by('id'))
    word_count = len(article.content.split()) if article.content else 0

    context = {
        'page_title': f'Extraction detail — {article.title[:50]}',
        'article': article,
        'incidents': incidents,
        'word_count': word_count,
    }
    return render(request, 'core/article_extraction_detail.html', context)
