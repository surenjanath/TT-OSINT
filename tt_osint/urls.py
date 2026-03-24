"""
URL configuration for tt_osint project.
"""
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include

from core import views as core_views
from core.sitemaps import IncidentSitemap, StaticViewSitemap, StorySitemap

sitemaps = {
    "static": StaticViewSitemap,
    "incidents": IncidentSitemap,
    "stories": StorySitemap,
}

urlpatterns = [
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    path('django-admin/', admin.site.urls),
    path('articles/', include('articles.urls')),
    path('', include('incidents.urls')),
]
