"""Small views not tied to incidents/articles domains."""
import os

from django.http import HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def robots_txt(request):
    """Tell crawlers what to index; point to sitemap."""
    base = os.environ.get("CANONICAL_SITE_URL", "").strip().rstrip("/")
    if not base:
        base = request.build_absolute_uri("/").rstrip("/")
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        "Disallow: /django-admin/",
        "Disallow: /api/",
        "Disallow: /admin-panel/",
        "Disallow: /operations/",
        "Disallow: /settings/",
        "Disallow: /articles/*/extraction-detail/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
