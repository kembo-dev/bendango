from django.urls import path

from .views import (
    scrape_view,
    search_history,
    search_run_detail,
    search_run_status,
)

urlpatterns = [
    path('', scrape_view, name='scrape_view'),
    path('searches/', search_history, name='search_history'),
    path('searches/<uuid:run_id>/', search_run_detail, name='search_run_detail'),
    path('api/search-runs/<uuid:run_id>/status/', search_run_status, name='search_run_status'),
]
