from django.contrib import admin
from tracker.models import PriceHistory, PriceListing, Product, Retailer


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'model', 'sku_or_ean', 'updated_at')
    search_fields = ('name', 'brand', 'model', 'sku_or_ean')


@admin.register(Retailer)
class RetailerAdmin(admin.ModelAdmin):
    list_display = ('name', 'base_url', 'is_active')
    search_fields = ('name', 'base_url')


@admin.register(PriceListing)
class PriceListingAdmin(admin.ModelAdmin):
    list_display = ('product', 'retailer', 'price', 'currency', 'normalized_price', 'normalized_currency', 'in_stock', 'scraped_at')
    list_filter = ('currency', 'in_stock', 'is_active', 'retailer')
    search_fields = ('product__name', 'retailer__name', 'url')


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('listing', 'price', 'currency', 'normalized_price', 'in_stock', 'recorded_at')
    list_filter = ('currency', 'in_stock', 'recorded_at')
    search_fields = ('listing__product__name', 'listing__retailer__name')
    readonly_fields = ('listing', 'price', 'currency', 'normalized_price', 'normalized_currency', 'in_stock', 'recorded_at')
