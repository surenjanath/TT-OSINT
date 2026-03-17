from django.contrib import admin
from .models import NewsSource, Article


@admin.register(NewsSource)
class NewsSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'scraper_type', 'is_active', 'last_checked')
    list_filter = ('scraper_type', 'is_active')
    search_fields = ('name',)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'source', 'published_date', 'is_processed')
    list_filter = ('source', 'is_processed')
    search_fields = ('title', 'content')
    date_hierarchy = 'published_date'
