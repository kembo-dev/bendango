from django.contrib import admin
from django.utils import timezone

from tracker.models import BusinessAccountRequest, BusinessProfile, PriceHistory, PriceListing, Product, Retailer, SearchDiagnostic, SearchRun


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'model', 'sku_or_ean', 'updated_at')
    search_fields = ('name', 'brand', 'model', 'sku_or_ean')


@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_url', 'trust_score', 'trust_level', 'is_active')
    list_filter = ('trust_level', 'is_active')
    search_fields = ('name', 'base_url')


@admin.register(PriceListing)
class PriceListingAdmin(admin.ModelAdmin):
    list_display = ('product', 'retailer', 'price', 'currency', 'normalized_price', 'normalized_currency', 'confidence_score', 'match_score', 'in_stock', 'is_active', 'scraped_at')
    list_filter = ('currency', 'extraction_source', 'in_stock', 'is_active', 'retailer')
    search_fields = ('product__name', 'retailer__name', 'url')


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('listing', 'price', 'currency', 'normalized_price', 'in_stock', 'recorded_at')
    list_filter = ('currency', 'in_stock', 'recorded_at')
    search_fields = ('listing__product__name', 'listing__retailer__name')
    readonly_fields = ('listing', 'price', 'currency', 'normalized_price', 'normalized_currency', 'in_stock', 'recorded_at')


@admin.register(SearchDiagnostic)
class SearchDiagnosticAdmin(admin.ModelAdmin):
    list_display = ('query', 'merchant_count', 'target_merchants', 'coverage_percent', 'offers_count', 'candidate_urls_count', 'processed_urls_count', 'duration_ms', 'created_at')
    list_filter = ('created_at', 'site_filter')
    search_fields = ('query', 'site_filter')
    readonly_fields = ('query', 'site_filter', 'search_terms_count', 'candidate_urls_count', 'processed_urls_count', 'fallback_urls_count', 'offers_count', 'merchant_count', 'target_merchants', 'coverage_ratio', 'rejection_reasons', 'duration_ms', 'created_at')

    @admin.display(description='Couverture')
    def coverage_percent(self, obj):
        return f'{obj.coverage_ratio * 100:.0f}%'



@admin.register(SearchRun)
class SearchRunAdmin(admin.ModelAdmin):
    list_display = ('query', 'user', 'market_code', 'status', 'created_at', 'completed_at')
    list_filter = ('market_code', 'status', 'created_at')
    search_fields = ('query', 'user__username', 'user__email')


@admin.register(BusinessAccountRequest)
class BusinessAccountRequestAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'business_type', 'status', 'created_at', 'reviewed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('business_name', 'business_type', 'user__username', 'user__email', 'phone', 'website')
    readonly_fields = ('created_at',)
    actions = ('approve_requests', 'reject_requests')

    @admin.action(description='Approuver les demandes sélectionnées')
    def approve_requests(self, request, queryset):
        reviewed_at = timezone.now()
        for item in queryset:
            item.status = BusinessAccountRequest.STATUS_APPROVED
            item.reviewed_at = reviewed_at
            item.save(update_fields=['status', 'reviewed_at'])

    @admin.action(description='Refuser les demandes sélectionnées')
    def reject_requests(self, request, queryset):
        reviewed_at = timezone.now()
        for item in queryset:
            item.status = BusinessAccountRequest.STATUS_REJECTED
            item.reviewed_at = reviewed_at
            item.save(update_fields=['status', 'reviewed_at'])


@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('business_name', 'user', 'business_type', 'market_code', 'country', 'retailer', 'is_verified', 'updated_at')
    list_filter = ('is_verified', 'market_code', 'country', 'business_type')
    search_fields = ('business_name', 'user__username', 'user__email', 'website', 'phone', 'country')
    readonly_fields = ('approved_request', 'retailer', 'created_at', 'updated_at')
