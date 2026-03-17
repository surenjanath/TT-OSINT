"""
URL configuration for tt_osint project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('articles/', include('articles.urls')),
    path('', include('incidents.urls')),
]
