"""
Views for the Trinidad Incident Intelligence Map.
"""
from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Count, Q, Avg, Sum
from django.db.models.functions import ExtractWeekDay, ExtractHour, TruncDate
from django.utils import timezone
from django.http import QueryDict
from datetime import timedelta, date as date_type
from itertools import groupby
import json

from .models import Incident, Person
from articles.models import Article, NewsSource, Story


def home_view(request):
    """National map dashboard — main landing page."""
    incidents = Incident.objects.filter(
        status__in=['approved', 'pending'],
        latitude__isnull=False,
        longitude__isnull=False,
    )

    # Stats for the sidebar
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    incidents_today = incidents.filter(incident_date__gte=today_start).count()
    yesterday_count = incidents.filter(
        incident_date__gte=yesterday_start,
        incident_date__lt=today_start,
    ).count()
    incidents_week = incidents.filter(incident_date__gte=week_ago).count()
    last_week_count = incidents.filter(
        incident_date__gte=two_weeks_ago,
        incident_date__lt=week_ago,
    ).count()

    # Week-over-week change (positive = up)
    if last_week_count:
        week_over_week_change = round((incidents_week - last_week_count) / last_week_count * 100)
    else:
        week_over_week_change = 0 if incidents_week == 0 else 100

    # Threat distribution: top 3–4 categories by count (with display names)
    cat_display = dict(Incident.CATEGORY_CHOICES)
    by_cat = (
        incidents.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')[:4]
    )
    total_for_pct = incidents.count() or 1
    threat_distribution = [
        {
            'name': cat_display.get(c['category'], c['category'].replace('_', ' ').title()),
            'count': c['count'],
            'pct': round(c['count'] / total_for_pct * 100),
        }
        for c in by_cat
    ]

    # Source health: active sources with last_checked (time since)
    active_sources_qs = NewsSource.objects.filter(is_active=True).order_by('name')
    source_health = []
    for src in active_sources_qs:
        if src.last_checked:
            delta = now - src.last_checked
            if delta.days > 0:
                since = f"{delta.days}d ago"
            elif delta.seconds >= 3600:
                since = f"{delta.seconds // 3600}h ago"
            else:
                since = "Recently"
            healthy = delta.days < 2  # considered healthy if checked in last 2 days
        else:
            since = "Never"
            healthy = False
        source_health.append({'name': src.name, 'since': since, 'healthy': healthy})

    # Severity breakdown: all 4 levels with count and pct
    sev_display = dict(Incident.SEVERITY_CHOICES)
    by_sev = list(
        incidents.values('severity').annotate(count=Count('id'))
    )
    sev_counts = {s['severity']: s['count'] for s in by_sev}
    severity_breakdown = []
    for sev_key, sev_label in Incident.SEVERITY_CHOICES:
        cnt = sev_counts.get(sev_key, 0)
        pct = round(cnt / total_for_pct * 100) if total_for_pct else 0
        severity_breakdown.append({
            'severity': sev_key,
            'label': sev_label,
            'count': cnt,
            'pct': pct,
        })

    # Region breakdown: top 5 regions by count
    region_display = dict(Incident.REGION_CHOICES)
    by_region_raw = list(
        incidents.values('region').annotate(count=Count('id')).order_by('-count')[:5]
    )
    region_breakdown = [
        {'name': region_display.get(r['region'], r['region']), 'count': r['count']}
        for r in by_region_raw
    ]
    region_max_count = by_region_raw[0]['count'] if by_region_raw else 1

    # Top hotspots: top 5 locations by count with region display
    top_hotspots_raw = list(
        incidents.filter(location_name__isnull=False)
        .exclude(location_name='')
        .values('location_name', 'region')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )
    top_hotspots = [
        {**h, 'region_display': region_display.get(h['region'], h['region'])}
        for h in top_hotspots_raw
    ]

    # Category chart data for sidebar donut (labels + values)
    by_cat_all = list(
        incidents.values('category')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    category_chart_data = {
        'labels': [cat_display.get(c['category'], c['category'].replace('_', ' ').title()) for c in by_cat_all],
        'values': [c['count'] for c in by_cat_all],
    }

    total_mapped = incidents.count()

    # Enriched stats: total victims, fatalities
    agg = incidents.aggregate(
        total_victims=Sum('victim_count'),
        total_fatalities=Sum('fatality_count'),
    )
    total_victims = agg['total_victims'] or 0
    total_fatalities = agg['total_fatalities'] or 0

    # JSON for home category donut (template-safe)
    context_category_chart_labels = json.dumps(category_chart_data['labels'])
    context_category_chart_values = json.dumps(category_chart_data['values'])

    context = {
        'page_title': 'Intelligence Map',
        'total_incidents': incidents.count(),
        'total_mapped': total_mapped,
        'incidents_today': incidents_today,
        'incidents_week': incidents_week,
        'yesterday_count': yesterday_count,
        'week_over_week_change': week_over_week_change,
        'articles_unprocessed': Article.objects.filter(is_processed=False).count(),
        'articles_total': Article.objects.count(),
        'incidents_pending': Incident.objects.filter(status='pending').count(),
        'critical_count': incidents.filter(severity='critical').count(),
        'high_count': incidents.filter(severity='high').count(),
        'total_victims': total_victims,
        'total_fatalities': total_fatalities,
        'categories': Incident.CATEGORY_CHOICES,
        'regions': Incident.REGION_CHOICES,
        'recent_incidents': incidents.order_by('-incident_date')[:10],
        'active_sources': active_sources_qs,
        'threat_distribution': threat_distribution,
        'source_health': source_health,
        'severities': Incident.SEVERITY_CHOICES,
        'severity_breakdown': severity_breakdown,
        'region_breakdown': region_breakdown,
        'region_max_count': region_max_count,
        'top_hotspots': top_hotspots,
        'category_chart_data': category_chart_data,
        'category_chart_data_labels': context_category_chart_labels,
        'category_chart_data_values': context_category_chart_values,
    }

    # Generate 7-day sparkline data
    sparkline_data = []
    for i in range(7):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = incidents.filter(
            incident_date__gte=day_start,
            incident_date__lt=day_end,
        ).count()
        sparkline_data.append(count)
    sparkline_data.reverse()
    context['sparkline_data'] = sparkline_data

    # Data freshness
    last_article = Article.objects.order_by('-scraped_date').first()
    last_incident = Incident.objects.order_by('-created_at').first()
    context['last_article_time'] = last_article.scraped_date if last_article else None
    context['last_incident_time'] = last_incident.created_at if last_incident else None

    return render(request, 'core/home.html', context)


def analytics_view(request):
    """Analytics dashboard with charts and KPI cards. Optimized for minimal DB queries."""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    thirty_days_ago = now - timedelta(days=30)

    incidents = Incident.objects.filter(status__in=['approved', 'pending'])

    # Single aggregate for all KPI counts (1 query)
    kpi = incidents.aggregate(
        total=Count('id'),
        today=Count('id', filter=Q(incident_date__gte=today_start)),
        week=Count('id', filter=Q(incident_date__gte=week_ago)),
        month=Count('id', filter=Q(incident_date__gte=month_ago)),
        critical=Count('id', filter=Q(severity='critical')),
        high=Count('id', filter=Q(severity='high')),
    )

    # Category, region, severity in 3 queries (unchanged but efficient)
    by_category = list(incidents.values('category').annotate(count=Count('id')).order_by('-count'))
    by_region = list(incidents.values('region').annotate(count=Count('id')).order_by('-count'))
    by_severity = list(incidents.values('severity').annotate(count=Count('id')).order_by('-count'))

    # Daily counts: one query with TruncDate, then fill 30-day list in Python
    daily_qs = incidents.filter(incident_date__gte=thirty_days_ago).annotate(
        date=TruncDate('incident_date')
    ).values('date').annotate(count=Count('id'))
    daily_by_date = {}
    for row in daily_qs:
        d = row['date']
        key = d.strftime('%Y-%m-%d') if d else ''
        if key:
            daily_by_date[key] = row['count']
    daily_counts = []
    for i in range(30):
        day = now - timedelta(days=29 - i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        date_str = day_start.strftime('%Y-%m-%d')
        daily_counts.append({
            'date': date_str,
            'label': day_start.strftime('%b %d'),
            'count': daily_by_date.get(date_str, 0),
        })

    # Article counts by published date (one query with TruncDate)
    article_qs = Article.objects.filter(
        published_date__isnull=False,
        published_date__gte=thirty_days_ago,
    ).annotate(
        date=TruncDate('published_date')
    ).values('date').annotate(count=Count('id'))
    article_by_date = {}
    for row in article_qs:
        d = row['date']
        key = d.strftime('%Y-%m-%d') if d else ''
        if key:
            article_by_date[key] = row['count']
    article_counts = []
    for i in range(30):
        day = now - timedelta(days=29 - i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        date_str = day_start.strftime('%Y-%m-%d')
        article_counts.append({
            'label': day_start.strftime('%b %d'),
            'count': article_by_date.get(date_str, 0),
        })

    # Top sources by incident count (1 query)
    top_sources = list(
        incidents.filter(primary_article__source__isnull=False)
        .values('primary_article__source__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # Top locations (hotspots) — 1 query
    region_display = dict(Incident.REGION_CHOICES)
    top_locations_raw = list(
        incidents.filter(location_name__isnull=False)
        .exclude(location_name='')
        .values('location_name', 'region')
        .annotate(count=Count('id'))
        .order_by('-count')[:8]
    )
    top_locations = [
        {**loc, 'region_display': region_display.get(loc['region'], loc['region'])}
        for loc in top_locations_raw
    ]

    # Day of week — 1 query
    by_weekday_raw = list(
        incidents.filter(incident_date__isnull=False)
        .annotate(weekday=ExtractWeekDay('incident_date'))
        .values('weekday')
        .annotate(count=Count('id'))
        .order_by('weekday')
    )
    weekday_labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
    by_weekday = [{'name': weekday_labels[i - 1], 'count': 0} for i in range(1, 8)]
    for r in by_weekday_raw:
        by_weekday[r['weekday'] - 1]['count'] = r['count']

    # Hour of day — 1 query
    by_hour_raw = list(
        incidents.filter(incident_date__isnull=False)
        .annotate(hour=ExtractHour('incident_date'))
        .values('hour')
        .annotate(count=Count('id'))
        .order_by('hour')
    )
    by_hour = [{'hour': h, 'count': 0} for h in range(24)]
    for r in by_hour_raw:
        by_hour[r['hour']]['count'] = r['count']

    # Confidence score buckets — 1 query
    conf_agg = incidents.aggregate(
        c1=Count('id', filter=Q(confidence_score__lte=25)),
        c2=Count('id', filter=Q(confidence_score__gt=25, confidence_score__lte=50)),
        c3=Count('id', filter=Q(confidence_score__gt=50, confidence_score__lte=75)),
        c4=Count('id', filter=Q(confidence_score__gt=75)),
    )
    confidence_buckets = [
        {'label': '0-25%', 'count': conf_agg['c1']},
        {'label': '26-50%', 'count': conf_agg['c2']},
        {'label': '51-75%', 'count': conf_agg['c3']},
        {'label': '76-100%', 'count': conf_agg['c4']},
    ]

    # Week-over-week and month-over-month — 1 aggregate each
    this_week_start = now - timedelta(days=now.weekday())
    this_week_start = this_week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    last_week_start = this_week_start - timedelta(days=7)
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_start = (this_month_start.replace(month=this_month_start.month - 1)
        if this_month_start.month > 1
        else this_month_start.replace(year=this_month_start.year - 1, month=12))
    week_month_agg = incidents.aggregate(
        this_week=Count('id', filter=Q(incident_date__gte=this_week_start)),
        last_week=Count('id', filter=Q(incident_date__gte=last_week_start, incident_date__lt=this_week_start)),
        this_month=Count('id', filter=Q(incident_date__gte=this_month_start)),
        last_month=Count('id', filter=Q(incident_date__gte=last_month_start, incident_date__lt=this_month_start)),
    )
    this_week_count = week_month_agg['this_week']
    last_week_count = week_month_agg['last_week']
    this_month_count = week_month_agg['this_month']
    last_month_count = week_month_agg['last_month']
    week_over_week_pct = round((this_week_count - last_week_count) / last_week_count * 100) if last_week_count else (0 if this_week_count == 0 else 100)
    month_over_month_pct = round((this_month_count - last_month_count) / last_month_count * 100) if last_month_count else (0 if this_month_count == 0 else 100)
    avg_per_day = kpi['month'] / 30.0

    # Category display name mapping
    cat_display = dict(Incident.CATEGORY_CHOICES)

    # Top 10 incident types — 1 query
    top_incident_types_raw = list(incidents.values('incident_type').annotate(count=Count('id')).order_by('-count')[:10])
    top_incident_types = [{'name': t['incident_type'], 'count': t['count']} for t in top_incident_types_raw]

    # Source performance — 1 annotated query (articles + incidents per source)
    source_perf_qs = NewsSource.objects.filter(is_active=True).annotate(
        art_count=Count('articles'),
        inc_count=Count('articles__incidents'),
    ).values('name', 'art_count', 'inc_count').order_by('-inc_count')
    source_performance = []
    for row in source_perf_qs:
        art_count = row['art_count']
        inc_count = row['inc_count']
        rate = round(inc_count / art_count * 100, 1) if art_count else 0
        source_performance.append({
            'name': row['name'],
            'articles': art_count,
            'incidents': inc_count,
            'extraction_rate': rate,
        })

    # Resolution stats — 1 aggregate (all statuses)
    res_agg = Incident.objects.aggregate(
        total=Count('id'),
        approved=Count('id', filter=Q(status='approved')),
        pending=Count('id', filter=Q(status='pending')),
        rejected=Count('id', filter=Q(status='rejected')),
    )
    total_all = res_agg['total'] or 0
    resolution_stats = [
        {'status': 'approved', 'label': 'Approved', 'count': res_agg['approved'], 'pct': round(res_agg['approved'] / total_all * 100) if total_all else 0},
        {'status': 'pending', 'label': 'Pending', 'count': res_agg['pending'], 'pct': round(res_agg['pending'] / total_all * 100) if total_all else 0},
        {'status': 'rejected', 'label': 'Rejected', 'count': res_agg['rejected'], 'pct': round(res_agg['rejected'] / total_all * 100) if total_all else 0},
    ]

    # Resolved / value stolen (Phase 4 analytics)
    resolved_agg = incidents.aggregate(
        resolved_count=Count('id', filter=Q(is_resolved=True)),
        value_stolen_total=Sum('value_stolen'),
    )
    resolved_count = resolved_agg['resolved_count'] or 0
    value_stolen_total = resolved_agg['value_stolen_total'] or 0
    by_premises = list(
        incidents.filter(premises_type__isnull=False)
        .exclude(premises_type='')
        .values('premises_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Person/victim demographics (Phase 3) — only from approved/pending incidents
    persons_qs = Person.objects.filter(incident__status__in=['approved', 'pending'])
    by_person_gender = list(
        persons_qs.values('gender').annotate(count=Count('id')).order_by('-count')
    )
    by_person_condition = list(
        persons_qs.values('condition').annotate(count=Count('id')).order_by('-count')
    )
    # Age buckets for distribution
    persons_with_age = persons_qs.filter(age__isnull=False).exclude(age__lt=0)
    age_buckets = [
        ('0-17', persons_with_age.filter(age__lte=17).count()),
        ('18-30', persons_with_age.filter(age__gte=18, age__lte=30).count()),
        ('31-50', persons_with_age.filter(age__gte=31, age__lte=50).count()),
        ('51+', persons_with_age.filter(age__gte=51).count()),
    ]
    person_demographics = {
        'by_gender': [{'name': g['gender'], 'count': g['count']} for g in by_person_gender],
        'by_condition': [{'name': c['condition'], 'count': c['count']} for c in by_person_condition],
        'age_buckets': age_buckets,
    }

    # Category trend: last 8 weeks — 8 queries (one per week, each returns category counts)
    cat_list = [c['category'] for c in by_category[:10]]
    category_trend_weeks = {'labels': [], 'datasets': []}
    for cat in cat_list:
        category_trend_weeks['datasets'].append({'name': cat_display.get(cat, cat), 'data': []})
    for w in range(8):
        week_end = now - timedelta(days=w * 7)
        week_start = week_end - timedelta(days=7)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_end.replace(hour=0, minute=0, second=0, microsecond=0)
        category_trend_weeks['labels'].insert(0, week_start.strftime('%b %d'))
        week_counts = dict(
            incidents.filter(
                incident_date__gte=week_start,
                incident_date__lt=week_end,
            ).values('category').annotate(count=Count('id')).values_list('category', 'count')
        )
        for i, cat in enumerate(cat_list):
            category_trend_weeks['datasets'][i]['data'].insert(0, week_counts.get(cat, 0))

    # Average confidence — 1 query
    avg_confidence_result = incidents.aggregate(avg=Avg('confidence_score'))
    avg_confidence = round(avg_confidence_result['avg'] or 0, 1)

    # Median response time: sample 500 rows to avoid loading thousands
    inc_with_dates = list(
        incidents.filter(incident_date__isnull=False)
        .values_list('incident_date', 'created_at')[:500]
    )
    deltas_h = []
    for inc_date, created in inc_with_dates:
        if created and inc_date:
            delta = created - inc_date
            deltas_h.append(delta.total_seconds() / 3600)
    if deltas_h:
        deltas_h.sort()
        mid = len(deltas_h) // 2
        median_hours = (deltas_h[mid] + deltas_h[mid - 1]) / 2 if len(deltas_h) % 2 == 0 else deltas_h[mid]
        median_response_hours = round(median_hours, 1)
    else:
        median_response_hours = None

    # Data freshness — 2 queries (indexed by scraped_date / created_at)
    last_article = Article.objects.order_by('-scraped_date').only('scraped_date').first()
    last_incident = Incident.objects.order_by('-created_at').only('created_at').first()
    data_freshness = {
        'last_article_at': last_article.scraped_date if last_article else None,
        'last_incident_at': last_incident.created_at if last_incident else None,
    }

    # Articles/sources count — 2 lightweight queries
    articles_count = Article.objects.count()
    sources_count = NewsSource.objects.filter(is_active=True).count()

    context = {
        'page_title': 'Analytics Dashboard',
        'total_incidents': kpi['total'],
        'incidents_today': kpi['today'],
        'incidents_week': kpi['week'],
        'incidents_month': kpi['month'],
        'critical_count': kpi['critical'],
        'high_count': kpi['high'],
        'articles_count': articles_count,
        'sources_count': sources_count,
        'by_category': [
            {'name': cat_display.get(c['category'], c['category']), 'count': c['count']}
            for c in by_category
        ],
        'by_region': [
            {'name': region_display.get(r['region'], r['region']), 'count': r['count']}
            for r in by_region
        ],
        'by_severity': list(by_severity),
        'daily_counts': daily_counts,
        'article_counts': article_counts,
        'top_sources': list(top_sources),
        'top_locations': top_locations,
        'by_weekday': by_weekday,
        'by_hour': by_hour,
        'confidence_buckets': confidence_buckets,
        'week_over_week_pct': week_over_week_pct,
        'avg_incidents_per_day': round(avg_per_day, 1),
        'month_over_month_pct': month_over_month_pct,
        'this_week_count': this_week_count,
        'last_week_count': last_week_count,
        'top_incident_types': top_incident_types,
        'source_performance': source_performance,
        'resolution_stats': resolution_stats,
        'category_trend_weeks': category_trend_weeks,
        'avg_confidence': avg_confidence,
        'median_response_hours': median_response_hours,
        'data_freshness': data_freshness,
        'resolved_count': resolved_count,
        'value_stolen_total': value_stolen_total,
        'by_premises': by_premises,
        'person_demographics': person_demographics,
    }
    return render(request, 'core/analytics.html', context)


def timeline_view(request):
    """Timeline page: articles in reverse-chronological order with nested incidents."""
    now = timezone.now()
    default_from = (now - timedelta(days=7)).date()
    default_to = now.date()

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    source_id = request.GET.get('source', '')
    category = request.GET.get('category', '')
    search = request.GET.get('search', '').strip()

    try:
        d_from = date_type.fromisoformat(date_from) if date_from else default_from
    except ValueError:
        d_from = default_from
    try:
        d_to = date_type.fromisoformat(date_to) if date_to else default_to
    except ValueError:
        d_to = default_to

    articles_qs = (
        Article.objects
        .filter(published_date__date__gte=d_from, published_date__date__lte=d_to)
        .select_related('source')
        .prefetch_related('incidents')
        .order_by('-published_date')
    )

    if source_id:
        articles_qs = articles_qs.filter(source_id=source_id)
    if search:
        articles_qs = articles_qs.filter(
            Q(title__icontains=search) | Q(content__icontains=search)
        )

    articles = list(articles_qs[:500])

    # Group by day
    def day_key(article):
        return article.published_date.date() if article.published_date else None

    grouped = []
    for day, group in groupby(articles, key=day_key):
        if day is None:
            continue
        day_articles = list(group)
        # Attach filtered incidents to each article if category filter is active
        for art in day_articles:
            if category:
                art.filtered_incidents = [
                    inc for inc in art.incidents.all() if inc.category == category
                ]
            else:
                art.filtered_incidents = list(art.incidents.all())
        grouped.append({
            'date': day,
            'articles': day_articles,
            'article_count': len(day_articles),
            'incident_count': sum(len(a.filtered_incidents) for a in day_articles),
        })

    total_articles = sum(g['article_count'] for g in grouped)
    total_incidents = sum(g['incident_count'] for g in grouped)

    # Build a flat chronological event list (oldest first) for the playback JS
    timeline_events = []
    for art in reversed(articles):
        incs = art.filtered_incidents if hasattr(art, 'filtered_incidents') else list(art.incidents.all())
        art_entry = {
            'type': 'article',
            'id': art.pk,
            'time': art.published_date.isoformat() if art.published_date else '',
            'title': art.title,
            'source': art.source.name if art.source else '',
            'summary': (art.summary or art.content or '')[:200],
            'url': art.url,
            'status': 'analyzed' if art.is_processed else ('failed' if art.processing_error else 'pending'),
            'incidents': [],
        }
        for inc in incs:
            art_entry['incidents'].append({
                'id': inc.pk,
                'incident_type': inc.incident_type,
                'category': inc.get_category_display(),
                'severity': inc.severity,
                'severity_color': inc.severity_color,
                'description': inc.description[:200],
                'location_name': inc.location_name or '',
                'region': inc.get_region_display(),
                'confidence': round(inc.confidence_score, 1),
                'lat': inc.latitude,
                'lng': inc.longitude,
                'victim_count': inc.victim_count,
                'fatality_count': inc.fatality_count,
                'weapon': inc.weapon,
            })
        timeline_events.append(art_entry)

    context = {
        'page_title': 'Timeline Analysis',
        'grouped_days': grouped,
        'total_articles': total_articles,
        'total_incidents': total_incidents,
        'sources': NewsSource.objects.filter(is_active=True).order_by('name'),
        'category_choices': Incident.CATEGORY_CHOICES,
        'timeline_events_json': json.dumps(timeline_events, default=str),
        'filters': {
            'date_from': d_from.isoformat(),
            'date_to': d_to.isoformat(),
            'source': source_id,
            'category': category,
            'search': search,
        },
    }
    return render(request, 'core/article_timeline.html', context)


def story_list_view(request):
    """List story clusters (articles grouped by same event)."""
    stories = (
        Story.objects
        .prefetch_related('articles', 'articles__source')
        .annotate(article_count=Count('articles'))
        .filter(article_count__gte=1)
        .order_by('-updated_at')
    )
    # Optional filter: only show multi-article stories
    multi_only = request.GET.get('multi', '')
    if multi_only == '1':
        stories = stories.filter(article_count__gte=2)
    paginator = Paginator(stories, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    context = {
        'page_title': 'Stories',
        'page_obj': page_obj,
        'total_count': paginator.count,
        'filters': {'multi': multi_only},
    }
    return render(request, 'core/story_list.html', context)


def story_detail_view(request, pk):
    """Single story: timeline of articles and combined incidents."""
    story = get_object_or_404(
        Story.objects.prefetch_related(
            'articles__source',
            'articles__incidents',
            'articles__linked_incidents',
        ).select_related('primary_incident'),
        pk=pk
    )
    articles = list(story.articles.all().order_by('published_date'))
    incident_ids = set()
    for a in articles:
        for inc in a.incidents.all():
            incident_ids.add(inc.pk)
        for inc in a.linked_incidents.all():
            incident_ids.add(inc.pk)
    incidents = list(Incident.objects.filter(pk__in=incident_ids).order_by('-incident_date')) if incident_ids else []
    context = {
        'page_title': story.title,
        'story': story,
        'articles': articles,
        'incidents': incidents,
    }
    return render(request, 'core/story_detail.html', context)


def incident_list_view(request):
    """Filterable incident list view with pagination."""
    incidents = (
        Incident.objects
        .select_related('primary_article', 'primary_article__source')
        .annotate(article_count=Count('related_articles'))
        .all()
    )

    # Apply filters
    status_filter = request.GET.get('status', '')
    category = request.GET.get('category')
    region = request.GET.get('region')
    severity = request.GET.get('severity')
    search = request.GET.get('search', '').strip()
    time_range = request.GET.get('time_range')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    is_resolved_filter = request.GET.get('is_resolved', '')

    if status_filter == 'all':
        pass  # show all statuses
    elif status_filter:
        incidents = incidents.filter(status=status_filter)
    else:
        incidents = incidents.filter(status='approved')
    if category:
        incidents = incidents.filter(category=category)
    if region:
        incidents = incidents.filter(region=region)
    if severity:
        incidents = incidents.filter(severity=severity)
    if search:
        incidents = incidents.filter(
            Q(incident_type__icontains=search) |
            Q(description__icontains=search) |
            Q(location_name__icontains=search)
        )
    if time_range:
        now = timezone.now()
        if time_range == '24h':
            incidents = incidents.filter(incident_date__gte=now - timedelta(hours=24))
        elif time_range == '7d':
            incidents = incidents.filter(incident_date__gte=now - timedelta(days=7))
        elif time_range == '30d':
            incidents = incidents.filter(incident_date__gte=now - timedelta(days=30))
    if date_from:
        incidents = incidents.filter(incident_date__gte=date_from)
    if date_to:
        incidents = incidents.filter(incident_date__lte=date_to + ' 23:59:59')
    if is_resolved_filter == '1':
        incidents = incidents.filter(is_resolved=True)
    elif is_resolved_filter == '0':
        incidents = incidents.filter(is_resolved=False)

    # Sortable columns
    sort_field = request.GET.get('sort', 'incident_date')
    order = request.GET.get('order', 'desc')
    valid_sorts = {'incident_date', 'created_at', 'severity', 'category', 'region', 'location_name', 'confidence_score', 'incident_type'}
    if sort_field not in valid_sorts:
        sort_field = 'incident_date'
    order_prefix = '' if order == 'asc' else '-'
    incidents = incidents.order_by(f'{order_prefix}{sort_field}')

    # Summary stats (severity and category breakdown of filtered set)
    severity_breakdown = list(
        incidents.values('severity').annotate(count=Count('id')).order_by('-count')
    )
    category_breakdown = list(
        incidents.values('category').annotate(count=Count('id')).order_by('-count')[:8]
    )
    sev_display = dict(Incident.SEVERITY_CHOICES)
    cat_display = dict(Incident.CATEGORY_CHOICES)
    severity_breakdown = [{'severity': s['severity'], 'label': sev_display.get(s['severity'], s['severity']), 'count': s['count']} for s in severity_breakdown]
    category_breakdown = [{'category': c['category'], 'label': cat_display.get(c['category'], c['category']), 'count': c['count']} for c in category_breakdown]

    total_count = incidents.count()

    # Build sort URLs for table headers (preserve filters, toggle order when same column)
    def _sort_url(col):
        q = QueryDict(mutable=True)
        if category:
            q['category'] = category
        if region:
            q['region'] = region
        if severity:
            q['severity'] = severity
        if search:
            q['search'] = search
        if time_range:
            q['time_range'] = time_range
        if status_filter:
            q['status'] = status_filter
        if date_from:
            q['date_from'] = date_from
        if date_to:
            q['date_to'] = date_to
        if is_resolved_filter:
            q['is_resolved'] = is_resolved_filter
        q['sort'] = col
        q['order'] = 'asc' if (sort_field == col and order == 'desc') else 'desc'
        return '?' + q.urlencode()

    sort_links = {
        'severity': _sort_url('severity'),
        'incident_type': _sort_url('incident_type'),
        'location_name': _sort_url('location_name'),
        'category': _sort_url('category'),
        'region': _sort_url('region'),
        'incident_date': _sort_url('incident_date'),
        'confidence_score': _sort_url('confidence_score'),
    }

    # Pagination
    paginator = Paginator(incidents, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_title': 'Incident List',
        'incidents': page_obj,
        'page_obj': page_obj,
        'total_count': total_count,
        'categories': Incident.CATEGORY_CHOICES,
        'regions': Incident.REGION_CHOICES,
        'severities': Incident.SEVERITY_CHOICES,
        'statuses': Incident.STATUS_CHOICES,
        'severity_breakdown': severity_breakdown,
        'category_breakdown': category_breakdown,
        'sort_field': sort_field,
        'sort_order': order,
        'sort_links': sort_links,
        'filters': {
            'category': category or '',
            'region': region or '',
            'severity': severity or '',
            'search': search,
            'time_range': time_range or '',
            'status': status_filter or '',
            'date_from': date_from,
            'date_to': date_to,
            'is_resolved': is_resolved_filter or '',
            'sort': sort_field,
            'order': order,
        },
    }
    return render(request, 'core/incident_list.html', context)


def incident_detail_view(request, pk):
    """Single incident detail page with related events."""
    incident = get_object_or_404(
        Incident.objects.select_related('primary_article', 'primary_article__source')
        .prefetch_related('related_articles', 'persons'),
        pk=pk
    )

    # Related incidents — same region or category, excluding self
    related = Incident.objects.filter(
        status='approved'
    ).exclude(pk=pk).filter(
        Q(region=incident.region) | Q(category=incident.category)
    ).order_by('-incident_date')[:5]

    # Location timeline: other incidents at same location (same location_name)
    location_timeline = []
    if incident.location_name:
        location_timeline = list(
            Incident.objects.filter(
                status='approved',
                location_name=incident.location_name,
            ).exclude(pk=pk).order_by('-incident_date')[:10]
        )

    # Nearby incidents count: same region, last 30 days, excluding self
    thirty_days_ago = timezone.now() - timedelta(days=30)
    nearby_incidents_count = Incident.objects.filter(
        status='approved',
        region=incident.region,
        incident_date__gte=thirty_days_ago,
    ).exclude(pk=pk).count()

    context = {
        'page_title': f'{incident.incident_type} — {incident.location_name}',
        'incident': incident,
        'related_incidents': related,
        'location_timeline': location_timeline,
        'nearby_incidents_count': nearby_incidents_count,
    }
    return render(request, 'core/incident_detail.html', context)


def admin_panel_view(request):
    """Admin moderation panel for reviewing incidents."""
    status_filter = request.GET.get('status', 'pending')
    search = request.GET.get('search', '').strip()

    if status_filter == 'all':
        incidents = Incident.objects.select_related('primary_article', 'primary_article__source').all()
    else:
        incidents = Incident.objects.select_related('primary_article', 'primary_article__source').filter(status=status_filter)

    if search:
        incidents = incidents.filter(
            Q(incident_type__icontains=search) |
            Q(description__icontains=search) |
            Q(location_name__icontains=search)
        )

    incidents = incidents.order_by('-created_at')

    # Auto-select first pending or specific incident
    selected_id = request.GET.get('selected')
    selected_incident = None
    if selected_id:
        try:
            selected_incident = Incident.objects.select_related('primary_article', 'primary_article__source').get(pk=selected_id)
        except Incident.DoesNotExist:
            pass
    elif incidents.exists():
        selected_incident = incidents.first()

    context = {
        'page_title': 'Moderation Panel',
        'incidents': incidents[:100],
        'total_count': incidents.count(),
        'pending_count': Incident.objects.filter(status='pending').count(),
        'approved_count': Incident.objects.filter(status='approved').count(),
        'rejected_count': Incident.objects.filter(status='rejected').count(),
        'status_filter': status_filter,
        'search': search,
        'selected_incident': selected_incident,
    }
    return render(request, 'core/admin_panel.html', context)


def operations_view(request):
    """Operations Center — pipeline controls, source management, activity log."""
    context = {
        'page_title': 'Operations Center',
        'articles_total': Article.objects.count(),
        'articles_unprocessed': Article.objects.filter(is_processed=False).count(),
        'incidents_total': Incident.objects.count(),
        'incidents_pending': Incident.objects.filter(status='pending').count(),
        'sources': NewsSource.objects.all().order_by('name'),
    }
    return render(request, 'core/operations.html', context)


def edit_source_view(request, pk):
    """Dedicated full-page view for editing a news source."""
    source = get_object_or_404(NewsSource, pk=pk)
    context = {
        'page_title': f'Edit Source: {source.name}',
        'source': source,
        'api_pagination': source.api_pagination or {},
        'api_date_range': source.api_date_range or {},
    }
    return render(request, 'core/edit_source.html', context)

from core.models import SystemSetting
from django.conf import settings

def settings_view(request):
    """Global system configuration panel."""
    from incidents.services import OllamaExtractor

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_settings':
            SystemSetting.set_setting('ollama_host', request.POST.get('ollama_host', 'http://localhost:11434'))
            SystemSetting.set_setting('ollama_model', request.POST.get('ollama_model', '').strip())
            SystemSetting.set_setting('scraper_timeout', request.POST.get('scraper_timeout', '10'))
            SystemSetting.set_setting('max_articles_per_feed', request.POST.get('max_articles_per_feed', '400000'))
            SystemSetting.set_setting('historical_date_from', request.POST.get('historical_date_from', '2020-01-01'))
            SystemSetting.set_setting('historical_max_pages', request.POST.get('historical_max_pages', '0'))
            # AI extractor settings
            SystemSetting.set_setting('ai_extractor_limit', request.POST.get('ai_extractor_limit', '15000'))
            SystemSetting.set_setting('ai_content_max_chars', request.POST.get('ai_content_max_chars', '6000'))
            SystemSetting.set_setting('ai_temperature', request.POST.get('ai_temperature', '0.1'))
            SystemSetting.set_setting('ai_num_predict', request.POST.get('ai_num_predict', '2000'))
            SystemSetting.set_setting('ai_timeout', request.POST.get('ai_timeout', '120'))
            custom_prompt = request.POST.get('ai_extraction_prompt', '').strip()
            if not custom_prompt or custom_prompt == OllamaExtractor.EXTRACTION_PROMPT.strip():
                SystemSetting.set_setting('ai_extraction_prompt', '')
            else:
                SystemSetting.set_setting('ai_extraction_prompt', custom_prompt)
            SystemSetting.set_setting('ai_prompt_version', OllamaExtractor.PROMPT_VERSION)
            # Geocoding
            SystemSetting.set_setting('google_maps_api_key', request.POST.get('google_maps_api_key', '').strip())
        elif action == 'clear_all_data':
            from articles.models import Article, ScrapeJob, NewsSource as NS2
            from incidents.models import Incident
            a_count = Article.objects.count()
            i_count = Incident.objects.count()
            j_count = ScrapeJob.objects.count()
            Article.objects.all().delete()
            Incident.objects.all().delete()
            ScrapeJob.objects.all().delete()
            NS2.objects.all().update(
                total_articles_scraped=0, oldest_article_date=None,
                newest_article_date=None, historical_complete=False,
            )
            from django.contrib import messages
            messages.success(request, f'Cleared {a_count} articles, {i_count} incidents, {j_count} scrape jobs. Source tracking reset.')

    # Load current settings with defaults
    context = {
        'page_title': 'System Settings',
        'ollama_host': SystemSetting.get_setting('ollama_host', getattr(settings, 'OLLAMA_HOST', 'http://localhost:11434')),
        'ollama_model': SystemSetting.get_setting('ollama_model', ''),
        'scraper_timeout': SystemSetting.get_setting('scraper_timeout', '10'),
        'max_articles_per_feed': SystemSetting.get_setting('max_articles_per_feed', '400000'),
        'historical_date_from': SystemSetting.get_setting('historical_date_from', '2020-01-01'),
        'historical_max_pages': SystemSetting.get_setting('historical_max_pages', '0'),
        'ai_extractor_limit': SystemSetting.get_setting('ai_extractor_limit', '15000'),
        'ai_content_max_chars': SystemSetting.get_setting('ai_content_max_chars', '6000'),
        'ai_temperature': SystemSetting.get_setting('ai_temperature', '0.1'),
        'ai_num_predict': SystemSetting.get_setting('ai_num_predict', '2000'),
        'ai_timeout': SystemSetting.get_setting('ai_timeout', '120'),
        'ai_extraction_prompt': (SystemSetting.get_setting('ai_extraction_prompt', '') or '').strip() or OllamaExtractor.EXTRACTION_PROMPT,
        'google_maps_api_key': SystemSetting.get_setting('google_maps_api_key', ''),
    }

    # Source tracking info
    from articles.models import NewsSource as NS, ScrapeJob
    source_stats = []
    for src in NS.objects.filter(is_active=True).order_by('name'):
        source_stats.append({
            'name': src.name,
            'scraper_type': src.scraper_type,
            'total_scraped': src.total_articles_scraped,
            'oldest_date': src.oldest_article_date,
            'newest_date': src.newest_article_date,
            'historical_complete': src.historical_complete,
            'last_checked': src.last_checked,
        })
    context['source_stats'] = source_stats
    context['recent_scrape_jobs'] = ScrapeJob.objects.select_related('source').all()[:25]

    # Counts for danger zone
    from articles.models import Article
    from incidents.models import Incident as Inc
    context['total_articles'] = Article.objects.count()
    context['total_incidents'] = Inc.objects.count()
    context['total_scrape_jobs'] = ScrapeJob.objects.count()

    return render(request, 'core/settings.html', context)
