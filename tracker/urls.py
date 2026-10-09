from django.contrib.auth import views as auth_views
from django.urls import path

from .publishing import publish_offer, my_announcements, edit_announcement, toggle_announcement

from .views import (
    pro_dashboard,
    pro_offer_boost_request,
    pro_offer_create,
    pro_offer_edit,
    pro_offer_media_action,
    pro_offer_toggle,
    pro_offers,
    public_offer,
    public_business,
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
    path('publish/', publish_offer, name='publish_offer'),
    path('account/announcements/', my_announcements, name='my_announcements'),
    path('account/announcements/<int:offer_id>/edit/', edit_announcement, name='edit_announcement'),
    path('account/announcements/<int:offer_id>/toggle/', toggle_announcement, name='toggle_announcement'),
    path('accounts/signup/', signup, name='signup'),
    path(
        'accounts/login/',
        auth_views.LoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('account/pro-request/', request_business_account, name='business_account_request'),
    path('pro/', pro_dashboard, name='pro_dashboard'),
    path('business/<slug:slug>/', public_business, name='public_business'),
    path('offer/<slug:slug>/', public_offer, name='public_offer'),
    path('pro/offers/', pro_offers, name='pro_offers'),
    path('pro/offers/add/', pro_offer_create, name='pro_offer_create'),
    path('pro/offers/<int:offer_id>/edit/', pro_offer_edit, name='pro_offer_edit'),
    path('pro/offers/<int:offer_id>/boost/', pro_offer_boost_request, name='pro_offer_boost_request'),
    path('pro/offers/<int:offer_id>/media/<int:media_id>/<str:action>/', pro_offer_media_action, name='pro_offer_media_action'),
    path('pro/offers/<int:offer_id>/toggle/', pro_offer_toggle, name='pro_offer_toggle'),
    path('pro/products/', pro_products, name='pro_products'),
    path('pro/products/add/', pro_product_create, name='pro_product_create'),
    path('pro/products/<int:listing_id>/edit/', pro_product_edit, name='pro_product_edit'),
    path('pro/products/<int:listing_id>/toggle/', pro_product_toggle, name='pro_product_toggle'),
    path('searches/', search_history, name='search_history'),
    path('searches/<uuid:run_id>/', search_run_detail, name='search_run_detail'),
    path('api/search-runs/<uuid:run_id>/status/', search_run_status, name='search_run_status'),
]
