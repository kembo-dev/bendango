from django.contrib.auth import views as auth_views
from django.urls import path

from .views import (
    pro_dashboard,
    pro_product_create,
    pro_product_edit,
    pro_product_toggle,
    pro_products,
    request_business_account,
    scrape_view,
    search_history,
    search_run_detail,
    search_run_status,
    signup,
)

urlpatterns = [
    path('', scrape_view, name='scrape_view'),
    path('accounts/signup/', signup, name='signup'),
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('account/pro-request/', request_business_account, name='business_account_request'),
    path('pro/', pro_dashboard, name='pro_dashboard'),
    path('pro/products/', pro_products, name='pro_products'),
    path('pro/products/add/', pro_product_create, name='pro_product_create'),
    path('pro/products/<int:listing_id>/edit/', pro_product_edit, name='pro_product_edit'),
    path('pro/products/<int:listing_id>/toggle/', pro_product_toggle, name='pro_product_toggle'),
    path('searches/', search_history, name='search_history'),
    path('searches/<uuid:run_id>/', search_run_detail, name='search_run_detail'),
    path('api/search-runs/<uuid:run_id>/status/', search_run_status, name='search_run_status'),
]
