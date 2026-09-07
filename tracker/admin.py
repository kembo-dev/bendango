from django.contrib import admin
from tracker.models import Product, Retailer, PriceListing, PriceHistory


admin.site.register(Product)
admin.site.register(Retailer)
admin.site.register(PriceListing)
admin.site.register(PriceHistory)
