from django.urls import path

from .views import scrape_view, search_run_status

urlpatterns = [
    path('', scrape_view, name='scrape_view'),
    path('api/search-runs/<uuid:run_id>/status/', search_run_status, name='search_run_status'),
]
