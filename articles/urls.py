"""
URL routing for the articles app.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.article_list_view, name='article_list'),
    path('<int:pk>/extraction-detail/', views.article_extraction_detail_view, name='article_extraction_detail'),
    path('<int:pk>/', views.article_detail_view, name='article_detail'),
]
