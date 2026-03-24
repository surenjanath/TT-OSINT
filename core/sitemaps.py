"""XML sitemaps for public indexable pages."""
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from articles.models import Story
from incidents.models import Incident


class StaticViewSitemap(Sitemap):
    """Main navigation pages."""

    changefreq = "daily"

    def items(self):
        return [
            ("home", 1.0),
            ("analytics", 0.8),
            ("timeline", 0.8),
            ("story_list", 0.8),
            ("incident_list", 0.9),
            ("article_list", 0.8),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]


class IncidentSitemap(Sitemap):
    """Approved incidents only (public-facing detail pages)."""
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return list(
            Incident.objects.filter(status="approved")
            .order_by("-updated_at")
            .only("pk", "updated_at")[:800]
        )

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("incident_detail", args=[obj.pk])


class StorySitemap(Sitemap):
    """Story cluster pages."""
    changefreq = "weekly"
    priority = 0.65

    def items(self):
        return list(Story.objects.order_by("-updated_at").only("pk", "updated_at")[:400])

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("story_detail", args=[obj.pk])
