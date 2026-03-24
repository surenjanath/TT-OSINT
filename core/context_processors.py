"""Template context for SEO (canonical / Open Graph base URL)."""
import os


def seo_context(request):
    """
    site_origin: base URL without trailing slash, for og:url and canonical.
    Prefer CANONICAL_SITE_URL in production (correct scheme/host behind proxies).
    """
    explicit = os.environ.get("CANONICAL_SITE_URL", "").strip().rstrip("/")
    if explicit:
        site_origin = explicit
    else:
        site_origin = request.build_absolute_uri("/").rstrip("/")
    return {
        "site_origin": site_origin,
    }
