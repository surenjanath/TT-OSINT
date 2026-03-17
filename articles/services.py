"""
News ingestion services — RSS parsing and web scraping.
With granular per-source and per-article logging callbacks.
"""
import json
import logging
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode

import feedparser
import requests
from bs4 import BeautifulSoup
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import NewsSource, Article

logger = logging.getLogger(__name__)

# Query params to strip for URL normalization (tracking, analytics)
TRACKING_PARAMS = frozenset([
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'ref', '_ga', 'mc_cid', 'mc_eid', 'utm_hp_ref',
])


def normalize_url(url: str) -> str:
    """Normalize URL for deduplication: strip tracking params, lowercase scheme/host, remove www."""
    if not url or not url.strip():
        return url or ''
    try:
        parsed = urlparse(url.strip())
        if not parsed.scheme or not parsed.netloc:
            return url.strip()
        # Drop tracking query params
        qs = parse_qs(parsed.query, keep_blank_values=False)
        filtered = {k: v for k, v in qs.items() if k.lower() not in TRACKING_PARAMS}
        new_query = urlencode(filtered, doseq=True)
        netloc = parsed.netloc.lower()
        if netloc.startswith('www.'):
            netloc = netloc[4:]
        return urlunparse((
            parsed.scheme.lower(),
            netloc,
            parsed.path.rstrip('/') or '/',
            parsed.params,
            new_query,
            '',
        ))
    except Exception:
        return url.strip()


def _request_with_retry(url, headers, timeout, max_attempts=3, log_fn=None):
    """GET request with exponential backoff retries."""
    last_error = None
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                delay = min(2 ** attempt, 10)
                time.sleep(delay)
                if log_fn:
                    log_fn(f'    Retry {attempt + 1}/{max_attempts} after {delay}s', 'info')
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            last_error = e
    raise last_error


def parse_flexible_date(date_str):
    """Parse a date string in various formats. Returns timezone-aware datetime or None."""
    if not date_str or not isinstance(date_str, str):
        return None
    date_str = date_str.strip()
    if not date_str:
        return None
    # Django's parse_datetime handles ISO 8601
    dt = parse_datetime(date_str)
    if dt:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt)
        return dt
    try:
        from dateutil.parser import parse as dateutil_parse
        dt = dateutil_parse(date_str)
        if dt:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
    except Exception:
        pass
    # Fallback: common formats without timezone (strptime)
    for fmt in ('%a, %d %b %Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%d %b %Y %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
            return dt
        except (ValueError, TypeError):
            continue
    return None

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}


class RSSFeedParser:
    """Parse RSS feeds and extract article metadata."""

    def fetch_articles(self, source: NewsSource, log_fn=None) -> list[dict]:
        """Fetch articles from an RSS feed source, with optional pagination (?paged=N)."""
        if not source.rss_url:
            if log_fn:
                log_fn(f'⚠️ [{source.name}] No RSS URL configured — skipping', 'warning')
            return []

        pagination = source.api_pagination or {}
        paginate = pagination.get('enabled', False)
        max_pages = int(pagination.get('max_pages', 1))
        if paginate and max_pages == 0:
            max_pages = 50  # safety limit for RSS
        elif not paginate:
            max_pages = 1

        all_articles = []
        for page_num in range(1, max_pages + 1):
            page_url = source.rss_url
            if page_num > 1:
                sep = '&' if '?' in page_url else '?'
                page_url = f"{page_url}{sep}paged={page_num}"

            page_articles = self._parse_single_feed(source, page_url, page_num, log_fn)

            if page_articles is None:
                break
            all_articles.extend(page_articles)

            if not page_articles:
                if log_fn and paginate:
                    log_fn(f'    ○ Page {page_num} returned 0 entries — stopping', 'info')
                break

            if not paginate:
                break
            if page_num < max_pages:
                time.sleep(1)

        if log_fn and paginate and max_pages > 1:
            log_fn(f'📦 [{source.name}] Total: {len(all_articles)} RSS articles across {min(page_num, max_pages)} page(s)', 'success')
        return all_articles

    def _parse_single_feed(self, source, feed_url, page_num, log_fn):
        """Parse a single RSS feed URL. Returns list of article dicts, or None on hard error."""
        try:
            if log_fn:
                label = f' page {page_num}' if page_num > 1 else ''
                log_fn(f'📡 [{source.name}] Connecting to RSS feed{label}...', 'info')

            start = time.time()

            try:
                resp = requests.get(feed_url, headers=HEADERS, timeout=20, verify=False)
                resp.raise_for_status()
                content = resp.content
            except requests.exceptions.RequestException as req_err:
                if log_fn:
                    log_fn(f'❌ [{source.name}] RSS fetch error: {req_err}', 'error')
                return None if page_num == 1 else []

            feed = feedparser.parse(content)

            # If feedparser fails on malformed XML, try sanitising with BeautifulSoup
            if feed.bozo and not feed.entries:
                try:
                    soup = BeautifulSoup(content, 'xml')
                    feed = feedparser.parse(str(soup))
                except Exception:
                    pass

            elapsed = time.time() - start

            if feed.bozo and not feed.entries:
                if log_fn:
                    log_fn(f'❌ [{source.name}] RSS parse error: {feed.bozo_exception}', 'error')
                return None if page_num == 1 else []

            articles = []
            for entry in feed.entries:
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        pub_date = timezone.make_aware(
                            datetime(*entry.published_parsed[:6])
                        )
                    except Exception:
                        pass
                if pub_date is None and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    try:
                        pub_date = timezone.make_aware(
                            datetime(*entry.updated_parsed[:6])
                        )
                    except Exception:
                        pass

                if pub_date is None and hasattr(entry, 'published') and entry.published:
                    pub_date = parse_flexible_date(entry.published)
                if pub_date is None and hasattr(entry, 'updated') and entry.updated:
                    pub_date = parse_flexible_date(entry.updated)

                content = ''
                if hasattr(entry, 'content') and entry.content:
                    content = entry.content[0].get('value', '')
                elif hasattr(entry, 'summary'):
                    content = entry.summary or ''

                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    content = soup.get_text(separator=' ', strip=True)

                summary = ''
                if hasattr(entry, 'summary') and entry.summary:
                    summary = entry.summary
                    if summary:
                        soup_s = BeautifulSoup(summary, 'html.parser')
                        summary = soup_s.get_text(separator=' ', strip=True)[:1000]

                tags_list = []
                if hasattr(entry, 'tags') and entry.tags:
                    for t in entry.tags:
                        term = t.get('term') if isinstance(t, dict) else getattr(t, 'term', None)
                        if term:
                            tags_list.append(str(term).strip())
                tags_str = ', '.join(tags_list)[:500] if tags_list else ''

                image_url = None
                if getattr(entry, 'media_thumbnail', None) and entry.media_thumbnail:
                    u = entry.media_thumbnail[0].get('url') if isinstance(entry.media_thumbnail[0], dict) else getattr(entry.media_thumbnail[0], 'url', None)
                    if u:
                        image_url = u
                if not image_url and getattr(entry, 'media_content', None) and entry.media_content:
                    m = entry.media_content[0]
                    url_attr = m.get('url') if isinstance(m, dict) else getattr(m, 'url', None)
                    if url_attr:
                        image_url = url_attr
                if not image_url and getattr(entry, 'enclosures', None) and entry.enclosures:
                    for enc in entry.enclosures:
                        href = enc.get('href') if isinstance(enc, dict) else getattr(enc, 'href', None)
                        enc_type = (enc.get('type') or '') if isinstance(enc, dict) else getattr(enc, 'type', '') or ''
                        if href and ('image' in enc_type or not enc_type):
                            image_url = href
                            break

                title = entry.get('title', '').strip()
                url = entry.get('link', '').strip()
                if title and url:
                    articles.append({
                        'title': title,
                        'url': url,
                        'content': content,
                        'author': entry.get('author', ''),
                        'published_date': pub_date,
                        'summary': summary,
                        'tags': tags_str,
                        'image_url': image_url,
                    })

            if log_fn:
                log_fn(
                    f'📰 [{source.name}] Found {len(articles)} entries in {elapsed:.1f}s',
                    'success' if articles else 'warning'
                )
            return articles

        except Exception as e:
            msg = f'❌ [{source.name}] RSS fetch failed: {e}'
            logger.error(msg)
            if log_fn:
                log_fn(msg, 'error')
            return None if page_num == 1 else []


class WebScraper:
    """Scrape article content from web pages."""

    def _extract_date_from_soup(self, soup: BeautifulSoup):
        """Extract publication date from article page HTML. Returns timezone-aware datetime or None."""
        # meta property="article:published_time"
        meta = soup.find('meta', attrs={'property': 'article:published_time'})
        if meta and meta.get('content'):
            dt = parse_flexible_date(meta['content'])
            if dt:
                return dt
        # meta name="date" or "pubdate" or "publishdate"
        for name in ('date', 'pubdate', 'publishdate', 'article:published_time'):
            meta = soup.find('meta', attrs={'name': name})
            if meta and meta.get('content'):
                dt = parse_flexible_date(meta['content'])
                if dt:
                    return dt
        # <time datetime="...">
        time_el = soup.find('time', datetime=True)
        if time_el and time_el.get('datetime'):
            dt = parse_flexible_date(time_el['datetime'])
            if dt:
                return dt
        # JSON-LD structured data
        for script in soup.find_all('script', type='application/ld+json'):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    for key in ('datePublished', 'uploadDate'):
                        if key in data and data[key]:
                            dt = parse_flexible_date(data[key])
                            if dt:
                                return dt
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'datePublished' in item and item['datePublished']:
                            dt = parse_flexible_date(item['datePublished'])
                            if dt:
                                return dt
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def fetch_article_content(self, url: str, log_fn=None, timeout=15):
        """Fetch full article text from a URL. Returns (content_str, published_date_or_none)."""
        try:
            start = time.time()
            response = _request_with_retry(url, HEADERS, timeout, log_fn=log_fn)
            elapsed = time.time() - start

            soup = BeautifulSoup(response.text, 'html.parser')
            published_date = self._extract_date_from_soup(soup)

            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                tag.decompose()

            article_body = (
                soup.find('article')
                or soup.find('div', class_='entry-content')
                or soup.find('div', class_='article-content')
                or soup.find('div', class_='post-content')
                or soup.find('div', class_='story-body')
                or soup.find('main')
            )

            if article_body:
                text = article_body.get_text(separator='\n', strip=True)
            else:
                text = soup.get_text(separator='\n', strip=True)

            lines = [line.strip() for line in text.split('\n') if line.strip()]
            result = '\n'.join(lines)

            if log_fn:
                word_count = len(result.split())
                log_fn(f'    📄 Scraped {word_count} words in {elapsed:.1f}s', 'info')

            return (result, published_date)

        except requests.exceptions.Timeout:
            if log_fn:
                log_fn(f'    ⏱️ Timeout scraping article ({timeout}s)', 'warning')
            return ('', None)
        except requests.exceptions.HTTPError as e:
            if log_fn:
                log_fn(f'    ⚠️ HTTP {e.response.status_code} for article', 'warning')
            return ('', None)
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            if log_fn:
                log_fn(f'    ❌ Scrape error: {type(e).__name__}', 'error')
            return ('', None)

    def fetch_links_from_search(self, source: NewsSource, log_fn=None, timeout=15) -> list[dict]:
        """Scrape article links from a search/listing page."""
        if not source.url:
            return []

        try:
            if log_fn:
                log_fn(f'🌐 [{source.name}] Scraping listing page...', 'info')

            start = time.time()
            response = requests.get(source.url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            elapsed = time.time() - start
            soup = BeautifulSoup(response.text, 'html.parser')

            articles = []
            for link in soup.find_all('a', href=True):
                href = link['href']
                title = link.get_text(strip=True)

                if not title or len(title) < 15:
                    continue
                if any(skip in href.lower() for skip in [
                    'javascript:', '#', 'mailto:', '/tag/',
                    '/category/', '/author/', '/page/',
                ]):
                    continue

                full_url = urljoin(source.url, href)
                articles.append({
                    'title': title,
                    'url': full_url,
                    'content': '',
                    'author': '',
                    'published_date': None,
                })

            seen = set()
            unique = []
            for a in articles:
                if a['url'] not in seen:
                    seen.add(a['url'])
                    unique.append(a)

            if log_fn:
                log_fn(
                    f'🌐 [{source.name}] Found {len(unique)} links in {elapsed:.1f}s',
                    'success' if unique else 'warning'
                )
            return unique[:20]

        except Exception as e:
            msg = f'❌ [{source.name}] Link scrape failed: {e}'
            logger.error(msg)
            if log_fn:
                log_fn(msg, 'error')
            return []


def _get_val(obj, path):
    if not path:
        return None
    parts = path.split('.')
    current = obj
    for p in parts:
        if isinstance(current, dict) and p in current:
            current = current[p]
        else:
            return None
    return current


# Absolute safety limit when max_pages=0 (unlimited pagination)
API_PAGINATION_SAFETY_LIMIT = 2000


class APIScraper:
    """Fetch and map JSON API responses into article format, with pagination."""

    @staticmethod
    def _inject_date_range(url, date_range_config, date_from, date_to):
        """Replace or append date range params in the URL based on config."""
        if not date_range_config or not date_from or not date_to:
            return url
        start_param = date_range_config.get('start_param', 'd1')
        end_param = date_range_config.get('end_param', 'd2')
        fmt = date_range_config.get('format', '%Y-%m-%d')
        parsed = urlparse(url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs[start_param] = [date_from.strftime(fmt)]
        qs[end_param] = [date_to.strftime(fmt)]
        new_query = urlencode(qs, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

    def fetch_articles(self, source: NewsSource, log_fn=None, timeout=15, date_from=None, date_to=None) -> list[dict]:
        """Fetch articles from a JSON API source, supporting multi-page pagination.
        Pagination types: offset (param=o), page (param=page), cursor (next_url from response).
        max_pages=0 means paginate until exhausted (with safety limit).
        date_from/date_to: optional date objects for date-range filtering via api_date_range config."""
        if not source.rss_url:
            if log_fn:
                log_fn(f'⚠️ [{source.name}] No API URL configured — skipping', 'warning')
            return []

        headers = source.api_headers if source.api_headers else HEADERS
        mapping = source.api_mapping or {}
        items_path = mapping.get('items_path', 'rows')
        title_field = mapping.get('title_field', 'title')
        url_field = mapping.get('url_field', 'url')
        content_field = mapping.get('content_field', 'presentation')
        author_field = mapping.get('author_field', 'author')
        date_field = mapping.get('date_field', 'published_date')
        tags_field = mapping.get('tags_field', '')
        image_field = mapping.get('image_field', '')
        summary_field = mapping.get('summary_field', '')

        # Date range: auto-resolve from source tracking or config defaults if not provided
        date_range_config = source.api_date_range
        if date_range_config:
            from datetime import date as _date, datetime as _dt
            if not date_from:
                if date_range_config.get('default_start'):
                    try:
                        date_from = _dt.strptime(date_range_config['default_start'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        date_from = _date(2020, 1, 1)
                elif source.newest_article_date:
                    date_from = source.newest_article_date.date()
                else:
                    date_from = _date(2020, 1, 1)
            if not date_to:
                if date_range_config.get('default_end'):
                    try:
                        date_to = _dt.strptime(date_range_config['default_end'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        date_to = _date.today()
                else:
                    date_to = _date.today()
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            if log_fn:
                log_fn(f'📅 [{source.name}] Date range: {date_from} → {date_to}', 'info')

        pagination = source.api_pagination or {}
        paginate = pagination.get('enabled', False)
        pagination_type = pagination.get('type', 'offset').lower()
        offset_param = pagination.get('param', 'o')
        page_size = int(pagination.get('page_size', 100))
        max_pages = int(pagination.get('max_pages', 1))
        initial_offset = int(pagination.get('initial_offset', 0))
        initial_page = int(pagination.get('initial_page', 1))
        next_field = pagination.get('next_field', 'next')

        # Unlimited: max_pages=0 means fetch until no more data, capped by safety limit
        if paginate and max_pages == 0:
            pages_to_fetch = API_PAGINATION_SAFETY_LIMIT
            unlimited = True
        elif paginate:
            pages_to_fetch = max_pages
            unlimited = False
        else:
            pages_to_fetch = 1
            unlimited = False

        all_articles = []
        page_num = 0
        next_url = None  # for cursor type

        while page_num < pages_to_fetch:
            # Build URL for this page
            if pagination_type == 'cursor' and next_url and page_num > 0:
                fetch_url = next_url
            else:
                base_url = source.rss_url
                if date_range_config:
                    base_url = self._inject_date_range(base_url, date_range_config, date_from, date_to)
                separator = '&' if '?' in base_url else '?'
                if paginate and pagination_type == 'page':
                    fetch_url = f"{base_url}{separator}{offset_param}={initial_page + page_num}"
                elif paginate and (pagination_type == 'offset' or pagination_type not in ('page', 'cursor')):
                    fetch_url = f"{base_url}{separator}{offset_param}={initial_offset + page_num * page_size}"
                else:
                    fetch_url = base_url

            try:
                if log_fn:
                    if paginate:
                        log_fn(f'🌐 [{source.name}] Fetching page {page_num + 1}...', 'info')
                    else:
                        log_fn(f'🌐 [{source.name}] Connecting to API...', 'info')

                start = time.time()
                response = _request_with_retry(fetch_url, headers, timeout, log_fn=log_fn)
                elapsed = time.time() - start
                data = response.json()

                # Cursor: resolve next URL from response for next iteration
                next_url = None
                if pagination_type == 'cursor' and isinstance(data, dict):
                    next_val = _get_val(data, next_field)
                    if next_val and isinstance(next_val, str) and next_val.startswith('http'):
                        next_url = next_val

                items = data
                if items_path:
                    for key in items_path.split('.'):
                        if isinstance(items, dict) and key in items:
                            items = items[key]
                        else:
                            items = []
                            break

                if not isinstance(items, list):
                    if log_fn:
                        log_fn(f'❌ [{source.name}] API data path "{items_path}" did not return a list', 'error')
                    break

                if not items:
                    if log_fn:
                        log_fn(f'    ○ Page {page_num + 1} returned 0 items — stopping', 'info')
                    break

                page_articles = self._parse_items(
                    items, source,
                    title_field, url_field, content_field, author_field, date_field,
                    tags_field=tags_field, image_field=image_field, summary_field=summary_field,
                )
                if log_fn:
                    log_fn(
                        f'📰 [{source.name}] Page {page_num + 1}: {len(page_articles)} items in {elapsed:.1f}s',
                        'success' if page_articles else 'warning'
                    )
                all_articles.extend(page_articles)

                # Stop if no more pages
                if len(items) < page_size:
                    if log_fn and paginate:
                        log_fn(f'    ○ Received {len(items)} items (< {page_size}) — stopping', 'info')
                    break
                if pagination_type == 'cursor' and not next_url:
                    if log_fn:
                        log_fn(f'    ○ No next URL — stopping', 'info')
                    break

                if not paginate:
                    break

                page_num += 1
                if paginate and page_num < pages_to_fetch:
                    time.sleep(1)
                if unlimited and page_num >= pages_to_fetch and log_fn:
                    log_fn(f'    ⚠️ Reached safety limit of {API_PAGINATION_SAFETY_LIMIT} pages', 'warning')

            except requests.exceptions.Timeout:
                if log_fn:
                    log_fn(f'    ⏱️ Timeout on page {page_num + 1} ({timeout}s)', 'warning')
                break
            except requests.exceptions.HTTPError as e:
                if log_fn:
                    log_fn(f'    ⚠️ HTTP {e.response.status_code} on page {page_num + 1}', 'warning')
                break
            except Exception as e:
                msg = f'❌ [{source.name}] API fetch failed on page {page_num + 1}: {e}'
                logger.error(msg)
                if log_fn:
                    log_fn(msg, 'error')
                break

        if log_fn and paginate:
            num_pages = page_num + 1
            log_fn(f'📦 [{source.name}] Total: {len(all_articles)} articles across {num_pages} page(s)', 'success')
        return all_articles

    def _parse_items(self, items, source, title_field, url_field, content_field, author_field, date_field,
                     tags_field='', image_field='', summary_field=''):
        """Parse a list of raw API items into article dicts."""
        articles = []
        for item in items:
            if not isinstance(item, dict):
                continue

            v_title = _get_val(item, title_field)
            title = str(v_title).strip() if v_title else ''

            v_url = _get_val(item, url_field)
            url = str(v_url).strip() if v_url else ''

            if not title or not url:
                continue

            if url.startswith('/'):
                url = urljoin(source.url, url)

            v_content = _get_val(item, content_field)
            content_html = ''
            if isinstance(v_content, list):
                content_html = '\n'.join(str(c) for c in v_content if c)
            elif v_content:
                content_html = str(v_content).strip()
            content = ''
            if content_html:
                soup = BeautifulSoup(content_html, 'html.parser')
                content = soup.get_text(separator='\n', strip=True)

            pub_date = None
            v_date = _get_val(item, date_field)
            if v_date is not None:
                if isinstance(v_date, (int, float)):
                    # Unix timestamp (milliseconds or seconds)
                    ts = v_date / 1000.0 if v_date > 1e12 else float(v_date)
                    try:
                        pub_date = timezone.make_aware(datetime.utcfromtimestamp(ts))
                    except Exception:
                        pass
                elif isinstance(v_date, str) and v_date.strip().isdigit():
                    ts = int(v_date)
                    ts = ts / 1000.0 if ts > 1e12 else float(ts)
                    try:
                        pub_date = timezone.make_aware(datetime.utcfromtimestamp(ts))
                    except Exception:
                        pass
                elif isinstance(v_date, str) and v_date.strip():
                    pub_date = parse_flexible_date(v_date.strip())

            v_author = _get_val(item, author_field)
            author = ''
            if isinstance(v_author, list):
                author = ', '.join(str(a).strip() for a in v_author if a)[:200]
            elif v_author:
                author = str(v_author).strip()

            tags_str = ''
            if tags_field:
                v_tags = _get_val(item, tags_field)
                if v_tags is not None:
                    if isinstance(v_tags, list):
                        tags_str = ', '.join(str(t).strip() for t in v_tags if t)[:500]
                    else:
                        tags_str = str(v_tags).strip()[:500]

            image_url = None
            if image_field:
                v_img = _get_val(item, image_field)
                if v_img and isinstance(v_img, str) and v_img.startswith(('http', '/')):
                    image_url = urljoin(source.url, v_img) if v_img.startswith('/') else v_img

            summary = ''
            if summary_field:
                v_sum = _get_val(item, summary_field)
                if v_sum:
                    summary = str(v_sum).strip()
                    if summary:
                        soup_s = BeautifulSoup(summary, 'html.parser')
                        summary = soup_s.get_text(separator=' ', strip=True)[:2000]

            articles.append({
                'title': title,
                'url': url,
                'content': content,
                'author': author,
                'published_date': pub_date,
                'tags': tags_str,
                'image_url': image_url,
                'summary': summary,
                'raw_api_item': item,
            })
        return articles


class ArticleIngestionService:
    """Orchestrate article ingestion from all active sources."""

    def __init__(self, log_fn=None):
        self.rss_parser = RSSFeedParser()
        self.web_scraper = WebScraper()
        self.api_scraper = APIScraper()
        self.log_fn = log_fn

    def _log(self, message, level='info'):
        if self.log_fn:
            self.log_fn(message, level)

    @staticmethod
    def _update_source_tracking(source, pub_date, new_count):
        """Update source's tracking fields after saving articles."""
        if pub_date:
            if source.oldest_article_date is None or pub_date < source.oldest_article_date:
                source.oldest_article_date = pub_date
            if source.newest_article_date is None or pub_date > source.newest_article_date:
                source.newest_article_date = pub_date
        source.total_articles_scraped += new_count

    def _create_scrape_job(self, source, date_from=None, date_to=None):
        from .models import ScrapeJob
        return ScrapeJob.objects.create(
            source=source, status='running',
            date_from=date_from, date_to=date_to,
        )

    def _finish_job(self, job, status, articles_found, articles_new, articles_skipped, errors, error_message=''):
        job.status = status
        job.finished_at = timezone.now()
        job.articles_found = articles_found
        job.articles_new = articles_new
        job.articles_skipped = articles_skipped
        job.errors = errors
        job.error_message = error_message
        job.save()

    def ingest_source(self, source) -> int:
        """Ingest articles from a single specific source. Returns count of new articles."""
        from core.models import SystemSetting
        from datetime import date as _date, datetime as _dt

        try:
            scraper_timeout = int(SystemSetting.get_setting('scraper_timeout', '10'))
        except Exception:
            scraper_timeout = 15

        date_from = None
        date_to = None
        if source.scraper_type == 'api' and source.api_date_range:
            dr = source.api_date_range
            # Prefer explicit default_start over newest_article_date so user's range (e.g. 2024-01-01 to 2024-12-31) is used
            if dr.get('default_start'):
                try:
                    date_from = _dt.strptime(dr['default_start'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    date_from = _date(2020, 1, 1)
            elif source.newest_article_date:
                date_from = source.newest_article_date.date()
            else:
                date_from = _date(2020, 1, 1)
            if dr.get('default_end'):
                try:
                    date_to = _dt.strptime(dr['default_end'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    date_to = _date.today()
            else:
                date_to = _date.today()
            if date_from > date_to:
                date_from, date_to = date_to, date_from

        job = self._create_scrape_job(source, date_from=date_from, date_to=date_to)

        source_start = time.time()
        source_new = 0
        source_skipped = 0
        total_errors = 0

        try:
            self._log(f'━━━ Targeted scrape: {source.name} ({source.scraper_type.upper()}) ━━━', 'info')

            if source.scraper_type == 'rss':
                raw_articles = self.rss_parser.fetch_articles(source, log_fn=self.log_fn)
            elif source.scraper_type == 'api':
                raw_articles = self.api_scraper.fetch_articles(
                    source, log_fn=self.log_fn, timeout=scraper_timeout,
                    date_from=date_from, date_to=date_to,
                )
            else:
                raw_articles = self.web_scraper.fetch_links_from_search(source, log_fn=self.log_fn, timeout=scraper_timeout)

            if not raw_articles:
                self._log(f'    ⚠️ No articles found from {source.name}', 'warning')
                source.last_checked = timezone.now()
                source.save(update_fields=['last_checked'])
                self._finish_job(job, 'completed', 0, 0, 0, 0)
                return 0

            max_articles = source.max_articles_per_scrape if source.max_articles_per_scrape else int(SystemSetting.get_setting('max_articles_per_feed', '400000'))
            raw_articles = raw_articles[:max_articles]
            job.articles_found = len(raw_articles)

            for j, raw in enumerate(raw_articles):
                if not raw['url']:
                    continue
                if Article.objects.filter(url=raw['url']).exists():
                    source_skipped += 1
                    continue
                normalized = normalize_url(raw['url'])
                if normalized != raw['url'] and Article.objects.filter(url=normalized).exists():
                    source_skipped += 1
                    continue

                content = raw.get('content', '')
                if len(content) < 100 and raw['url']:
                    self._log(f'    📄 [{j+1}/{len(raw_articles)}] Fetching full text for: {raw["title"][:60]}...', 'info')
                    content, scraped_date = self.web_scraper.fetch_article_content(raw['url'], log_fn=self.log_fn, timeout=scraper_timeout)
                    if scraped_date and not raw.get('published_date'):
                        raw['published_date'] = scraped_date

                try:
                    create_kwargs = {
                        'title': raw['title'][:500],
                        'content': content,
                        'url': raw['url'],
                        'source': source,
                        'author': raw.get('author', '')[:200],
                        'published_date': raw.get('published_date'),
                        'tags': raw.get('tags', '')[:500],
                        'image_url': raw.get('image_url') or None,
                        'summary': (raw.get('summary') or '')[:2000],
                    }
                    if source.scraper_type == 'api' and 'raw_api_item' in raw:
                        create_kwargs['raw_api_data'] = raw['raw_api_item']
                    Article.objects.create(**create_kwargs)
                    source_new += 1
                    self._update_source_tracking(source, raw.get('published_date'), 1)
                except Exception as e:
                    total_errors += 1
                    self._log(f'    ❌ Failed to save: {type(e).__name__}: {e}', 'error')

            source_elapsed = time.time() - source_start
            self._log(
                f'    ✅ {source.name}: +{source_new} new, {source_skipped} duplicates skipped ({source_elapsed:.1f}s)',
                'success' if source_new else 'info'
            )

            source.last_checked = timezone.now()
            source.save(update_fields=[
                'last_checked', 'oldest_article_date', 'newest_article_date', 'total_articles_scraped',
            ])
            self._finish_job(job, 'completed', len(raw_articles), source_new, source_skipped, total_errors)
        except Exception as e:
            self._log(f'    ❌ Scrape job failed: {e}', 'error')
            self._finish_job(job, 'failed', 0, source_new, source_skipped, total_errors, error_message=str(e))
        return source_new

    def ingest_all(self) -> int:
        """Ingest articles from all active sources. Returns count of new articles."""
        from core.models import SystemSetting
        from datetime import date as _date, datetime as _dt

        try:
            scraper_timeout = int(SystemSetting.get_setting('scraper_timeout', '10'))
        except Exception:
            scraper_timeout = 15

        sources = list(NewsSource.objects.filter(is_active=True))
        total_new = 0
        total_skipped = 0
        total_errors = 0
        pipeline_start = time.time()

        self._log(f'🚀 Starting ingestion — {len(sources)} active source(s)', 'info')

        for i, source in enumerate(sources):
            source_start = time.time()
            source_new = 0
            source_skipped = 0

            date_from = None
            date_to = None
            if source.scraper_type == 'api' and source.api_date_range:
                dr = source.api_date_range
                if dr.get('default_start'):
                    try:
                        date_from = _dt.strptime(dr['default_start'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        date_from = _date(2020, 1, 1)
                elif source.newest_article_date:
                    date_from = source.newest_article_date.date()
                else:
                    date_from = _date(2020, 1, 1)
                if dr.get('default_end'):
                    try:
                        date_to = _dt.strptime(dr['default_end'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        date_to = _date.today()
                else:
                    date_to = _date.today()
                if date_from > date_to:
                    date_from, date_to = date_to, date_from

            job = self._create_scrape_job(source, date_from=date_from, date_to=date_to)

            try:
                self._log(f'━━━ Source {i+1}/{len(sources)}: {source.name} ({source.scraper_type.upper()}) ━━━', 'info')

                if source.scraper_type == 'rss':
                    raw_articles = self.rss_parser.fetch_articles(source, log_fn=self.log_fn)
                elif source.scraper_type == 'api':
                    raw_articles = self.api_scraper.fetch_articles(
                        source, log_fn=self.log_fn, timeout=scraper_timeout,
                        date_from=date_from, date_to=date_to,
                    )
                else:
                    raw_articles = self.web_scraper.fetch_links_from_search(source, log_fn=self.log_fn, timeout=scraper_timeout)

                if not raw_articles:
                    self._log(f'    ⚠️ No articles found from {source.name}', 'warning')
                    source.last_checked = timezone.now()
                    source.save(update_fields=['last_checked'])
                    self._finish_job(job, 'completed', 0, 0, 0, 0)
                    continue

                max_articles = source.max_articles_per_scrape if source.max_articles_per_scrape else int(SystemSetting.get_setting('max_articles_per_feed', '400000'))
                raw_articles = raw_articles[:max_articles]

                for j, raw in enumerate(raw_articles):
                    if not raw['url']:
                        continue
                    if Article.objects.filter(url=raw['url']).exists():
                        source_skipped += 1
                        continue
                    normalized = normalize_url(raw['url'])
                    if normalized != raw['url'] and Article.objects.filter(url=normalized).exists():
                        source_skipped += 1
                        continue

                    content = raw.get('content', '')
                    if len(content) < 100 and raw['url']:
                        self._log(f'    📄 [{j+1}/{len(raw_articles)}] Fetching full text for: {raw["title"][:60]}...', 'info')
                        content, scraped_date = self.web_scraper.fetch_article_content(raw['url'], log_fn=self.log_fn, timeout=scraper_timeout)
                        if scraped_date and not raw.get('published_date'):
                            raw['published_date'] = scraped_date

                    try:
                        create_kwargs = {
                            'title': raw['title'][:500],
                            'content': content,
                            'url': raw['url'],
                            'source': source,
                            'author': raw.get('author', '')[:200],
                            'published_date': raw.get('published_date'),
                            'tags': raw.get('tags', '')[:500],
                            'image_url': raw.get('image_url') or None,
                            'summary': (raw.get('summary') or '')[:2000],
                        }
                        if source.scraper_type == 'api' and 'raw_api_item' in raw:
                            create_kwargs['raw_api_data'] = raw['raw_api_item']
                        Article.objects.create(**create_kwargs)
                        source_new += 1
                        self._update_source_tracking(source, raw.get('published_date'), 1)
                    except Exception as e:
                        total_errors += 1
                        self._log(f'    ❌ Failed to save: {type(e).__name__}: {e}', 'error')

                source_elapsed = time.time() - source_start
                total_new += source_new
                total_skipped += source_skipped

                self._log(
                    f'    ✅ {source.name}: +{source_new} new, {source_skipped} duplicates skipped ({source_elapsed:.1f}s)',
                    'success' if source_new else 'info'
                )

                source.last_checked = timezone.now()
                source.save(update_fields=[
                    'last_checked', 'oldest_article_date', 'newest_article_date', 'total_articles_scraped',
                ])
                self._finish_job(job, 'completed', len(raw_articles), source_new, source_skipped, total_errors)
            except Exception as e:
                self._log(f'    ❌ Scrape job failed for {source.name}: {e}', 'error')
                self._finish_job(job, 'failed', 0, source_new, source_skipped, total_errors, error_message=str(e))

        total_elapsed = time.time() - pipeline_start
        self._log(
            f'🏁 Ingestion complete in {total_elapsed:.1f}s — '
            f'{total_new} new articles, {total_skipped} duplicates, {total_errors} errors',
            'success' if total_new else 'warning'
        )

        logger.info(f"Ingestion complete: {total_new} new articles in {total_elapsed:.1f}s")
        return total_new
