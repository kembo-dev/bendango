from django.contrib import admin
from tracker.models import PriceHistory, PriceListing, Product, Retailer, SearchDiagnostic


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
