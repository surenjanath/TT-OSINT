"""
URL routing for the Trinidad Incident Intelligence Map.
"""
from django.urls import path
from . import views, api

urlpatterns = [
    # ─── Pages ─────────────────────────────────────────────
    path('', views.home_view, name='home'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('timeline/', views.timeline_view, name='timeline'),
    path('stories/', views.story_list_view, name='story_list'),
    path('stories/<int:pk>/', views.story_detail_view, name='story_detail'),
    path('incidents/', views.incident_list_view, name='incident_list'),
    path('incidents/<int:pk>/', views.incident_detail_view, name='incident_detail'),
    path('admin-panel/', views.admin_panel_view, name='admin_panel'),
    path('operations/', views.operations_view, name='operations'),
    path('operations/source/<int:pk>/edit/', views.edit_source_view, name='edit_source_view'),
    path('settings/', views.settings_view, name='settings'),

    # ─── API: Map & Stats ──────────────────────────────────
    path('api/incidents/geojson/', api.incidents_geojson, name='api_geojson'),
    path('api/incidents/export/', api.incidents_export_csv, name='api_export_csv'),
    path('api/incidents/stats/', api.incidents_stats, name='api_stats'),

    # ─── API: Pipeline Operations ──────────────────────────
    path('api/pipeline/scrape/', api.trigger_scrape, name='api_scrape'),
    path('api/pipeline/extract/', api.trigger_extract, name='api_extract'),
    path('api/pipeline/full/', api.trigger_full_pipeline, name='api_full_pipeline'),
    path('api/pipeline/reanalyze/<int:pk>/', api.reanalyze_article, name='api_reanalyze_article'),
    path('api/pipeline/status/', api.pipeline_status, name='api_pipeline_status'),

    # ─── API: Source Management ────────────────────────────
    path('api/sources/', api.list_sources, name='api_list_sources'),
    path('api/sources/test/', api.test_source_config, name='api_test_source'),
    path('api/sources/fetch-sample/', api.fetch_api_sample, name='api_fetch_sample'),
    path('api/sources/add/', api.add_source, name='api_add_source'),
    path('api/sources/<int:pk>/edit/', api.edit_source, name='api_edit_source'),
    path('api/sources/<int:pk>/toggle/', api.toggle_source, name='api_toggle_source'),
    path('api/sources/<int:pk>/delete/', api.delete_source, name='api_delete_source'),

    # ─── API: Moderation ───────────────────────────────────
    path('api/incidents/<int:pk>/moderate/', api.incident_moderate, name='api_moderate'),
    path('api/incidents/batch-moderate/', api.batch_moderate, name='api_batch_moderate'),
    path('api/incidents/<int:pk>/delete/', api.delete_incident, name='api_delete_incident'),
    path('api/incidents/<int:pk>/regeocode/', api.regeocode_incident, name='api_regeocode_incident'),
    path('api/incidents/regeocode-all/', api.regeocode_all_incidents, name='api_regeocode_all'),

    # ─── API: Settings ─────────────────────────────────────
    path('api/settings/ollama-models/', api.fetch_ollama_models, name='api_ollama_models'),
    path('api/settings/test-ai/', api.test_ai_connection, name='api_test_ai'),
]
