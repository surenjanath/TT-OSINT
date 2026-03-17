"""
JSON API endpoints — map data, pipeline operations, source management, moderation.
"""
import json
import threading
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from datetime import timedelta

from .models import Incident
from articles.models import Article, NewsSource

logger = logging.getLogger(__name__)

# ═══════════════════ Pipeline state (in-memory) ═══════════════
_pipeline_state = {
    'scraping': False,
    'extracting': False,
    'last_scrape': None,
    'last_extract': None,
    'last_scrape_count': 0,
    'last_extract_count': 0,
    'scrape_error': '',
    'extract_error': '',
    'log': [],  # activity log entries
}

MAX_LOG_ENTRIES = 100

def _add_log(message, level='info'):
    """Append a log entry to the in-memory activity log."""
    _pipeline_state['log'].insert(0, {
        'time': timezone.now().strftime('%H:%M:%S'),
        'message': message,
        'level': level,
    })
    _pipeline_state['log'] = _pipeline_state['log'][:MAX_LOG_ENTRIES]


# ═══════════════════ Map & Stats ══════════════════════════════

@require_GET
def incidents_geojson(request):
    """Return approved incidents as GeoJSON for Leaflet map."""
    incidents = Incident.objects.filter(
        status='approved',
        latitude__isnull=False,
        longitude__isnull=False,
    )

    category = request.GET.get('category')
    region = request.GET.get('region')
    severity = request.GET.get('severity')
    time_range = request.GET.get('time_range')

    if category:
        incidents = incidents.filter(category=category)
    if region:
        incidents = incidents.filter(region=region)
    if severity:
        incidents = incidents.filter(severity=severity)
    if time_range:
        now = timezone.now()
        deltas = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30)}
        if time_range in deltas:
            incidents = incidents.filter(incident_date__gte=now - deltas[time_range])
            
    # Advanced Custom Date Filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_from, '%Y-%m-%d')
            dt = timezone.make_aware(dt)
            incidents = incidents.filter(incident_date__gte=dt)
        except ValueError:
            pass
            
    if date_to:
        try:
            from datetime import datetime
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            # Set to end of day
            dt = timezone.make_aware(dt) + timedelta(days=1) - timedelta(seconds=1)
            incidents = incidents.filter(incident_date__lte=dt)
        except ValueError:
            pass

    features = [f for f in (inc.to_geojson_feature() for inc in incidents) if f]

    return JsonResponse({'type': 'FeatureCollection', 'features': features})


@require_GET
def incidents_export_csv(request):
    """Download approved incidents as a CSV file matching map filters."""
    import csv
    from django.http import HttpResponse
    
    incidents = Incident.objects.filter(status='approved')

    # Apply identical map filters
    category = request.GET.get('category')
    region = request.GET.get('region')
    severity = request.GET.get('severity')
    time_range = request.GET.get('time_range')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    if category: incidents = incidents.filter(category=category)
    if region: incidents = incidents.filter(region=region)
    if severity: incidents = incidents.filter(severity=severity)
    
    if time_range:
        now = timezone.now()
        deltas = {'24h': timedelta(hours=24), '7d': timedelta(days=7), '30d': timedelta(days=30)}
        if time_range in deltas:
            incidents = incidents.filter(incident_date__gte=now - deltas[time_range])
            
    if date_from:
        try:
            from datetime import datetime
            dt = timezone.make_aware(datetime.strptime(date_from, '%Y-%m-%d'))
            incidents = incidents.filter(incident_date__gte=dt)
        except ValueError: pass
            
    if date_to:
        try:
            from datetime import datetime
            dt = timezone.make_aware(datetime.strptime(date_to, '%Y-%m-%d')) + timedelta(days=1, seconds=-1)
            incidents = incidents.filter(incident_date__lte=dt)
        except ValueError: pass

    # Build CSV Response
    response = HttpResponse(
        content_type='text/csv',
        headers={'Content-Disposition': 'attachment; filename="incidents_export.csv"'},
    )
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Date', 'Severity', 'Category', 'Type', 'Location', 'Latitude', 'Longitude', 'Confidence'])
    
    for inc in incidents.order_by('-incident_date'):
        writer.writerow([
            inc.id,
            inc.incident_date.strftime('%Y-%m-%d %H:%M') if inc.incident_date else 'Unknown',
            inc.severity.upper(),
            inc.get_category_display(),
            inc.incident_type,
            inc.location_name,
            inc.latitude,
            inc.longitude,
            f"{inc.confidence_score:.1f}%"
        ])
        
    return response


@require_GET
def incidents_stats(request):
    """Aggregated stats for analytics."""
    incidents = Incident.objects.filter(status='approved')
    now = timezone.now()
    from django.db.models import Count

    return JsonResponse({
        'total': incidents.count(),
        'today': incidents.filter(incident_date__gte=now.replace(hour=0, minute=0, second=0)).count(),
        'week': incidents.filter(incident_date__gte=now - timedelta(days=7)).count(),
        'by_category': list(incidents.values('category').annotate(count=Count('id')).order_by('-count')),
        'by_region': list(incidents.values('region').annotate(count=Count('id')).order_by('-count')),
        'by_severity': list(incidents.values('severity').annotate(count=Count('id')).order_by('-count')),
    })


# ═══════════════════ Pipeline Operations ══════════════════════

def _run_scrape(source_id=None):
    """Background scraping job — feeds per-source logs into the activity log.
    If source_id is provided, only scrapes that specific NewsSource.
    """
    import time as _time
    _pipeline_state['scraping'] = True
    _pipeline_state['scrape_error'] = ''
    _pipeline_state['scrape_start'] = timezone.now().strftime('%H:%M:%S')
    _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
    if source_id:
        _add_log(f'🔄 TARGETED SCRAPING PIPELINE STARTED (Source ID: {source_id})', 'info')
    else:
        _add_log('🔄 NEWS SCRAPING PIPELINE STARTED', 'info')
    _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
    start = _time.time()
    try:
        from articles.services import ArticleIngestionService
        service = ArticleIngestionService(log_fn=_add_log)
        
        if source_id:
            try:
                source = NewsSource.objects.get(id=source_id)
                count = service.ingest_source(source)
            except NewsSource.DoesNotExist:
                _add_log(f"❌ Target Source ID {source_id} not found", 'error')
                count = 0
        else:
            count = service.ingest_all()
            
        elapsed = _time.time() - start
        _pipeline_state['last_scrape'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        _pipeline_state['last_scrape_count'] = count
        _pipeline_state['last_scrape_elapsed'] = f'{elapsed:.1f}s'
    except Exception as e:
        _pipeline_state['scrape_error'] = str(e)
        _add_log(f'❌ Scraping pipeline crashed: {e}', 'error')
        logger.error(f'Scrape error: {e}', exc_info=True)
    finally:
        _pipeline_state['scraping'] = False


def _run_extract():
    """Background AI extraction job — feeds per-article logs into the activity log."""
    import time as _time
    _pipeline_state['extracting'] = True
    _pipeline_state['extract_error'] = ''
    _pipeline_state['extract_start'] = timezone.now().strftime('%H:%M:%S')
    _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
    _add_log('🤖 AI EXTRACTION PIPELINE STARTED', 'info')
    _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
    start = _time.time()
    try:
        from incidents.services import IncidentProcessorService
        from core.models import SystemSetting
        limit = int(SystemSetting.get_setting('ai_extractor_limit', '1000'))
        limit = max(1, min(5000, limit))
        _add_log(f'Processing up to {limit} articles (Settings > AI Extractor limit)', 'info')
        service = IncidentProcessorService(log_fn=_add_log)
        count = service.process_unprocessed_articles(limit=limit)
        elapsed = _time.time() - start
        _pipeline_state['last_extract'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        _pipeline_state['last_extract_count'] = count
        _pipeline_state['last_extract_elapsed'] = f'{elapsed:.1f}s'
    except Exception as e:
        _pipeline_state['extract_error'] = str(e)
        _add_log(f'❌ Extraction pipeline crashed: {e}', 'error')
        logger.error(f'Extract error: {e}', exc_info=True)
    finally:
        _pipeline_state['extracting'] = False


@csrf_exempt
@require_POST
def trigger_scrape(request):
    """Trigger news scraping in a background thread.
    Can accept 'source_id' in POST body for targeted scraping.
    """
    if _pipeline_state['scraping']:
        return JsonResponse({'status': 'busy', 'message': 'Scraping already in progress'})

    source_id = None
    try:
        body = json.loads(request.body)
        source_id = body.get('source_id')
    except (json.JSONDecodeError, AttributeError):
        pass

    thread = threading.Thread(target=_run_scrape, args=(source_id,), daemon=True)
    thread.start()
    msg = f'Targeted scraping started for Source {source_id}' if source_id else 'News scraping started'
    return JsonResponse({'status': 'started', 'message': msg})


@csrf_exempt
@require_POST
def trigger_extract(request):
    """Trigger AI extraction in a background thread."""
    if _pipeline_state['extracting']:
        return JsonResponse({'status': 'busy', 'message': 'Extraction already in progress'})

    thread = threading.Thread(target=_run_extract, daemon=True)
    thread.start()
    return JsonResponse({'status': 'started', 'message': 'AI extraction started'})


@csrf_exempt
@require_POST
def trigger_full_pipeline(request):
    """Run scrape → extract sequentially in background."""
    if _pipeline_state['scraping'] or _pipeline_state['extracting']:
        return JsonResponse({'status': 'busy', 'message': 'Pipeline already running'})

    def _full():
        _run_scrape()
        _run_extract()

    thread = threading.Thread(target=_full, daemon=True)
    thread.start()
    return JsonResponse({'status': 'started', 'message': 'Full pipeline started (scrape → extract)'})

@csrf_exempt
@require_POST
def reanalyze_article(request, pk):
    """Re-analyze a specific article for incidents."""
    from django.shortcuts import get_object_or_404
    from incidents.services import IncidentProcessorService
    
    article = get_object_or_404(Article, pk=pk)
    
    def _reanalyze():
        _pipeline_state['extracting'] = True
        _pipeline_state['extract_start'] = timezone.now().strftime('%H:%M:%S')
        _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
        _add_log(f'🤖 RE-ANALYZING ARTICLE #{article.id}', 'info')
        _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
        
        try:
            # Delete old pending incidents from this article to avoid duplicates.
            # Approved or rejected incidents are kept, pending ones are cleared.
            deleted_count, _ = Incident.objects.filter(primary_article=article, status='pending').delete()
            if deleted_count > 0:
                _add_log(f'    🧹 Cleared {deleted_count} previous pending incidents.', 'info')

            service = IncidentProcessorService(log_fn=_add_log)
            # Process this single article
            count = service._process_single_article(article)
            
            # Mark as processed and clear any previous failure
            article.processing_error = ''
            article.is_processed = True
            article.save(update_fields=['processing_error', 'is_processed'])
            
            _pipeline_state['last_extract'] = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            
        except Exception as e:
            _add_log(f'❌ Re-analysis failed: {e}', 'error')
            logger.error(f'Re-analysis error on article {article.id}: {e}', exc_info=True)
            article.processing_error = str(e)[:500]
            article.save(update_fields=['processing_error'])
        finally:
            _pipeline_state['extracting'] = False

    if _pipeline_state['extracting']:
        return JsonResponse({'status': 'busy', 'message': 'Pipeline is currently busy.'}, status=429)

    thread = threading.Thread(target=_reanalyze, daemon=True)
    thread.start()
    return JsonResponse({'status': 'started', 'message': f'Re-analysis for article #{pk} started'})


@csrf_exempt
@require_POST
def regeocode_incident(request, pk):
    """Re-geocode a single incident using stored location text. Returns new coords and moved_km."""
    from django.shortcuts import get_object_or_404
    from .services import GeocodingService

    incident = get_object_or_404(Incident, pk=pk)
    loc = incident.ai_location_raw or incident.location_name or ''
    city = incident.ai_city or ''

    if not loc.strip():
        return JsonResponse({
            'status': 'error',
            'message': 'No location text to geocode (ai_location_raw and location_name are empty).',
        }, status=400)

    old_lat, old_lng = incident.latitude, incident.longitude
    geo = GeocodingService()
    result = geo.geocode(loc, city)

    if result['latitude'] is None:
        return JsonResponse({
            'status': 'error',
            'message': 'Geocoding could not resolve this address.',
            'old_lat': old_lat,
            'old_lng': old_lng,
        }, status=200)

    incident.latitude = result['latitude']
    incident.longitude = result['longitude']
    incident.region = result['region']
    incident.save(update_fields=['latitude', 'longitude', 'region'])

    moved_km = None
    if old_lat is not None and old_lng is not None:
        moved_km = ((result['latitude'] - old_lat) ** 2 + (result['longitude'] - old_lng) ** 2) ** 0.5 * 111  # approx km

    return JsonResponse({
        'status': 'ok',
        'old_lat': old_lat,
        'old_lng': old_lng,
        'new_lat': result['latitude'],
        'new_lng': result['longitude'],
        'region': result['region'],
        'moved_km': round(moved_km, 2) if moved_km is not None else None,
    })


@csrf_exempt
@require_POST
def regeocode_all_incidents(request):
    """Re-geocode all incidents in a background thread. Progress in Activity Log."""
    from .services import GeocodingService

    def _regeocode_all():
        _pipeline_state['extracting'] = True
        _pipeline_state['extract_start'] = timezone.now().strftime('%H:%M:%S')
        _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')
        _add_log('Re-geocoding all incidents...', 'info')
        _add_log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info')

        try:
            geo = GeocodingService()
            incidents = list(Incident.objects.all().order_by('pk'))
            total = len(incidents)
            updated = 0
            for i, inc in enumerate(incidents):
                loc = inc.ai_location_raw or inc.location_name or ''
                city = inc.ai_city or ''
                if not loc.strip():
                    continue
                old_lat, old_lng = inc.latitude, inc.longitude
                result = geo.geocode(loc, city)
                if result['latitude'] is None:
                    continue
                inc.latitude = result['latitude']
                inc.longitude = result['longitude']
                inc.region = result['region']
                inc.save(update_fields=['latitude', 'longitude', 'region'])
                updated += 1
                if old_lat is not None and old_lng is not None:
                    moved = ((result['latitude'] - old_lat) ** 2 + (result['longitude'] - old_lng) ** 2) ** 0.5 * 111
                    _add_log(f'  [{i+1}/{total}] #{inc.pk} moved {moved:.1f} km', 'info')
                else:
                    _add_log(f'  [{i+1}/{total}] #{inc.pk} set', 'info')

            _add_log(f'Done. Updated {updated}/{total} incidents.', 'success')
        except Exception as e:
            _add_log(f'Re-geocode all failed: {e}', 'error')
            logger.error('Re-geocode all error', exc_info=True)
        finally:
            _pipeline_state['extracting'] = False

    if _pipeline_state['extracting']:
        return JsonResponse({'status': 'busy', 'message': 'Pipeline is currently busy.'}, status=429)

    thread = threading.Thread(target=_regeocode_all, daemon=True)
    thread.start()
    return JsonResponse({'status': 'started', 'message': 'Re-geocode all started. Check Activity Log.'})


@require_GET
def pipeline_status(request):
    """Return current pipeline state with detailed metrics."""
    return JsonResponse({
        'scraping': _pipeline_state['scraping'],
        'extracting': _pipeline_state['extracting'],
        'last_scrape': _pipeline_state['last_scrape'],
        'last_extract': _pipeline_state['last_extract'],
        'last_scrape_count': _pipeline_state['last_scrape_count'],
        'last_extract_count': _pipeline_state['last_extract_count'],
        'last_scrape_elapsed': _pipeline_state.get('last_scrape_elapsed', ''),
        'last_extract_elapsed': _pipeline_state.get('last_extract_elapsed', ''),
        'scrape_start': _pipeline_state.get('scrape_start', ''),
        'extract_start': _pipeline_state.get('extract_start', ''),
        'scrape_error': _pipeline_state['scrape_error'],
        'extract_error': _pipeline_state['extract_error'],
        'articles_total': Article.objects.count(),
        'articles_unprocessed': Article.objects.filter(is_processed=False).count(),
        'articles_processed': Article.objects.filter(is_processed=True).count(),
        'incidents_total': Incident.objects.count(),
        'incidents_pending': Incident.objects.filter(status='pending').count(),
        'incidents_approved': Incident.objects.filter(status='approved').count(),
        'incidents_rejected': Incident.objects.filter(status='rejected').count(),
        'sources_active': NewsSource.objects.filter(is_active=True).count(),
        'sources_total': NewsSource.objects.count(),
        'log': _pipeline_state['log'][:80],
    })


# ═══════════════════ Source Management ════════════════════════

@require_GET
def list_sources(request):
    """Return all news sources as JSON."""
    sources = NewsSource.objects.all().order_by('name')
    data = []
    for s in sources:
        data.append({
            'id': s.id,
            'name': s.name,
            'url': s.url,
            'rss_url': s.rss_url or '',
            'scraper_type': s.scraper_type,
            'api_headers': s.api_headers,
            'api_mapping': s.api_mapping,
            'api_pagination': s.api_pagination,
            'api_date_range': s.api_date_range,
            'is_active': s.is_active,
            'last_checked': s.last_checked.strftime('%Y-%m-%d %H:%M') if s.last_checked else 'Never',
            'article_count': s.articles.count(),
        })
    return JsonResponse({'sources': data})


@csrf_exempt
@require_POST
def toggle_source(request, pk):
    """Toggle a source's active status."""
    try:
        source = NewsSource.objects.get(pk=pk)
    except NewsSource.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    source.is_active = not source.is_active
    source.save(update_fields=['is_active'])
    status_text = 'enabled' if source.is_active else 'disabled'
    _add_log(f'📡 Source "{source.name}" {status_text}', 'info')
    return JsonResponse({'status': 'ok', 'is_active': source.is_active, 'name': source.name})


@csrf_exempt
@require_POST
def add_source(request):
    """Add a new news source."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = data.get('name', '').strip()
    url = data.get('url', '').strip()
    rss_url = data.get('rss_url', '').strip()
    scraper_type = data.get('scraper_type', 'rss')
    
    api_headers = data.get('api_headers', None)
    api_mapping = data.get('api_mapping', None)
    api_pagination = data.get('api_pagination', None)
    api_date_range = data.get('api_date_range', None)
    
    limit_val = data.get('max_articles_per_scrape', '')
    max_articles_per_scrape = None
    if limit_val:
        try:
            max_articles_per_scrape = int(limit_val)
        except ValueError:
            pass

    if not name or not url:
        return JsonResponse({'error': 'Name and URL are required'}, status=400)

    defaults = {
        'url': url,
        'rss_url': rss_url,
        'scraper_type': scraper_type,
        'api_headers': api_headers,
        'api_mapping': api_mapping,
        'api_pagination': api_pagination,
        'api_date_range': api_date_range,
        'max_articles_per_scrape': max_articles_per_scrape,
    }
    source, created = NewsSource.objects.get_or_create(
        name=name,
        defaults=defaults,
    )
    if created:
        _add_log(f'📡 New source added: "{name}"', 'success')
    return JsonResponse({
        'status': 'created' if created else 'exists',
        'id': source.id,
        'name': source.name,
    })

@csrf_exempt
@require_POST
def edit_source(request, pk):
    """Edit an existing news source."""
    from django.shortcuts import get_object_or_404
    
    source = get_object_or_404(NewsSource, pk=pk)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = data.get('name', '').strip()
    url = data.get('url', '').strip()
    rss_url = data.get('rss_url', '').strip()
    scraper_type = data.get('scraper_type', 'rss')

    api_headers = data.get('api_headers', None)
    api_mapping = data.get('api_mapping', None)
    api_pagination = data.get('api_pagination', None)
    api_date_range = data.get('api_date_range', None)
    
    limit_val = data.get('max_articles_per_scrape', '')
    max_articles_per_scrape = None
    if limit_val:
        try:
            max_articles_per_scrape = int(limit_val)
        except ValueError:
            pass

    if not name or not url:
        return JsonResponse({'error': 'Name and URL are required'}, status=400)

    source.name = name
    source.url = url
    source.rss_url = rss_url
    source.scraper_type = scraper_type
    if api_headers is not None:
        source.api_headers = api_headers
    if api_mapping is not None:
        source.api_mapping = api_mapping
    if api_pagination is not None:
        source.api_pagination = api_pagination
    if api_date_range is not None:
        source.api_date_range = api_date_range
    source.max_articles_per_scrape = max_articles_per_scrape
    source.save()
    
    _add_log(f'📡 Source modified: "{name}"', 'info')
    
    return JsonResponse({
        'status': 'ok',
        'id': source.id,
        'name': source.name,
    })


@csrf_exempt
@require_POST
def delete_source(request, pk):
    """Delete a news source."""
    try:
        source = NewsSource.objects.get(pk=pk)
    except NewsSource.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    name = source.name
    source.delete()
    _add_log(f'🗑️ Source deleted: "{name}"', 'warning')
    return JsonResponse({'status': 'ok'})


# ═══════════════════ Source Test & Sample ══════════════════════

@csrf_exempt
def test_source_config(request):
    """Temporarily run scraper and return first 3 articles based on config without saving."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        rss_url = data.get('rss_url', '').strip()
        scraper_type = data.get('scraper_type', 'rss')
        api_headers = data.get('api_headers', None)
        api_mapping = data.get('api_mapping', None)
        api_pagination = data.get('api_pagination', None)
        api_date_range = data.get('api_date_range', None)
        
        if not url:
            return JsonResponse({'error': 'URL is required for test'}, status=400)
            
        from articles.models import NewsSource
        from articles.services import RSSFeedParser, WebScraper, APIScraper
        
        source = NewsSource(
            name='Test Preview',
            url=url,
            rss_url=rss_url,
            scraper_type=scraper_type,
            api_headers=api_headers,
            api_mapping=api_mapping,
            api_pagination=api_pagination,
            api_date_range=api_date_range,
        )
        
        articles = []
        if scraper_type == 'rss':
            scraper = RSSFeedParser()
            articles = scraper.fetch_articles(source)
        elif scraper_type == 'api':
            scraper = APIScraper()
            articles = scraper.fetch_articles(source, timeout=10)
        elif scraper_type == 'web':
            scraper = WebScraper()
            articles = scraper.fetch_links_from_search(source, timeout=10)
            
        preview = []
        for a in articles[:3]:
            content = a.get('content', '')
            if len(content) < 100 and a.get('url'):
                web_scraper = WebScraper()
                result = web_scraper.fetch_article_content(a['url'], timeout=10)
                full_content = result[0] if isinstance(result, tuple) else result
                if full_content:
                    content = full_content
            
            pub_date = a.get('published_date')
            pub_str = 'Unknown'
            if pub_date:
                try:
                    pub_str = pub_date.strftime('%Y-%m-%d %H:%M')
                except Exception:
                    pub_str = str(pub_date)

            preview.append({
                'title': a.get('title', 'Unknown Title'),
                'url': a.get('url', ''),
                'author': a.get('author', ''),
                'content_preview': content[:300] + '...' if len(content) > 300 else content,
                'published_date': pub_str,
                'tags': a.get('tags', ''),
                'image_url': a.get('image_url', ''),
            })
            
        return JsonResponse({
            'success': True,
            'total_found': len(articles),
            'articles': preview
        })
    except Exception as e:
        import traceback
        return JsonResponse({'error': f'Test Failed: {str(e)}', 'details': traceback.format_exc()}, status=500)


def _find_array_in_json(data, max_depth=3, current_depth=0, current_path=""):
    """
    Recursively search a JSON structure for the largest array of objects.
    Returns (path_string, list_of_objects).
    """
    if current_depth > max_depth or not data:
        return None, []
        
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        return current_path, data
        
    if isinstance(data, dict):
        best_path = None
        best_array = []
        for key, val in data.items():
            new_path = f"{current_path}.{key}" if current_path else key
            path, arr = _find_array_in_json(val, max_depth, current_depth + 1, new_path)
            if len(arr) > len(best_array):
                best_array = arr
                best_path = path
        return best_path, best_array
        
    return None, []

def _extract_keys(obj, prefix=''):
    """Flatten a nested dictionary into a list of dot-notation keys."""
    keys = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{prefix}.{k}" if prefix else k
            keys.append(new_key)
            
            if isinstance(v, dict):
                keys.extend(_extract_keys(v, new_key))
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                keys.extend(_extract_keys(v[0], new_key))
                
    # preserve order, remove duplicates
    return list(dict.fromkeys(keys))

def _get_val(obj, path):
    """Safely get a value from a nested dict using a dot-notation path."""
    parts = path.split('.')
    current = obj
    for p in parts:
        if isinstance(current, dict) and p in current:
            current = current[p]
        else:
            return None
    return current

@csrf_exempt
def fetch_api_sample(request):
    """Fetch sample data from an API source to populate visual mapping fields."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        url = data.get('url', '').strip()
        rss_url = data.get('rss_url', '').strip()
        scraper_type = data.get('scraper_type', 'rss')
        api_headers = data.get('api_headers', None)
        
        target_url = rss_url if rss_url else url
        if not target_url or scraper_type != 'api':
            return JsonResponse({'error': 'Valid API URL required'}, status=400)
            
        import requests
        
        headers = {}
        if api_headers and isinstance(api_headers, dict):
            headers = api_headers
        if 'User-Agent' not in headers:
             headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/100.0.0.0 Safari/537.36'
            
        response = requests.get(target_url, headers=headers, timeout=12)
        response.raise_for_status()
        json_data = response.json()
        
        # Auto-detect the array of items
        items_path, array_data = _find_array_in_json(json_data)
        
        if not array_data:
             return JsonResponse({'error': 'Could not auto-detect a main data array in the API response. Make sure this API returns a list of items.'}, status=400)
             
        # Extract keys from the first item
        sample_item = array_data[0]
        keys = _extract_keys(sample_item)
        
        # Flatten sample item for display
        sample_display = {}
        for k in keys:
            val = _get_val(sample_item, k)
            if val is not None:
                 val_str = str(val)[:100] + ('...' if len(str(val)) > 100 else '')
                 sample_display[k] = val_str
        
        return JsonResponse({
            'success': True,
            'items_path': items_path or '',
            'keys': keys,
            'sample_item': sample_display
        })
        
    except requests.exceptions.HTTPError as e:
         return JsonResponse({'error': f'API returned {e.response.status_code}', 'details': e.response.text[:500]}, status=500)
    except json.JSONDecodeError:
         return JsonResponse({'error': 'Failed to parse JSON. Did the URL return HTML instead?'}, status=500)
    except Exception as e:
        import traceback
        return JsonResponse({'error': f'Fetch Failed: {str(e)}', 'details': traceback.format_exc()}, status=500)


@require_GET
def fetch_ollama_models(request):
    """Return list of model names available on the given Ollama host."""
    import requests
    host = (request.GET.get('host') or 'http://localhost:11434').strip().rstrip('/')
    if not host.startswith('http'):
        return JsonResponse({'error': 'Invalid host URL'}, status=400)
    try:
        response = requests.get(f"{host}/api/tags", timeout=8)
        response.raise_for_status()
        data = response.json()
        # Ollama returns { "models": [ { "name": "model:tag", ... }, ... ] }
        models = [m.get('name', '') for m in data.get('models', []) if m.get('name')]
        return JsonResponse({'models': models})
    except requests.exceptions.ConnectionError:
        return JsonResponse({'error': 'Could not connect to Ollama. Is it running?'}, status=502)
    except requests.exceptions.Timeout:
        return JsonResponse({'error': 'Ollama host timed out.'}, status=504)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def test_ai_connection(request):
    """Test connection to the Ollama API with provided host and model."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        host = data.get('host', 'http://localhost:11434').rstrip('/')
        model = data.get('model', 'llama3')
        
        # Ping the /api/tags endpoint to check if the model is installed
        import requests
        response = requests.get(f"{host}/api/tags", timeout=5)
        response.raise_for_status()
        
        models = [m['name'] for m in response.json().get('models', [])]
        
        # Exact match or with 'latest' tag trick
        if model in models or f"{model}:latest" in models:
            return JsonResponse({'status': 'ok'})
        else:
            return JsonResponse({
                'status': 'error', 
                'message': f"Model '{model}' is not pulled on this Ollama host. Run `ollama pull {model}`"
            })
            
    except requests.exceptions.ConnectionError:
        return JsonResponse({'status': 'error', 'message': 'Could not connect to Ollama Host. Is it running?'})
    except requests.exceptions.Timeout:
        return JsonResponse({'status': 'error', 'message': 'Ollama Host timed out.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ═══════════════════ Moderation ═══════════════════════════════

@csrf_exempt
@require_POST
def incident_moderate(request, pk):
    """Approve or reject a single incident."""
    try:
        incident = Incident.objects.get(pk=pk)
        data = json.loads(request.body) if request.body else {}
        action = data.get('action', '')

        if action == 'approve':
            incident.status = 'approved'
            incident.save(update_fields=['status'])
            return JsonResponse({'status': 'ok', 'new_status': 'approved'})
        elif action == 'reject':
            incident.status = 'rejected'
            incident.save(update_fields=['status'])
            return JsonResponse({'status': 'ok', 'new_status': 'rejected'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)
    except Incident.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Incident not found'}, status=404)


@csrf_exempt
@require_POST
def batch_moderate(request):
    """Batch approve or reject all pending incidents."""
    data = json.loads(request.body) if request.body else {}
    action = data.get('action', '')

    pending = Incident.objects.filter(status='pending')
    count = pending.count()

    if action == 'approve_all':
        pending.update(status='approved')
        return JsonResponse({'status': 'ok', 'count': count, 'action': 'approved'})
    elif action == 'reject_all':
        pending.update(status='rejected')
        return JsonResponse({'status': 'ok', 'count': count, 'action': 'rejected'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid action'}, status=400)


@csrf_exempt
@require_POST
def delete_incident(request, pk):
    """Permanently delete an incident."""
    try:
        incident = Incident.objects.get(pk=pk)
        incident.delete()
        return JsonResponse({'status': 'ok'})
    except Incident.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Incident not found'}, status=404)

