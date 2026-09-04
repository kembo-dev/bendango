from django.contrib import admin
from tracker.models import Product, Retailer, PriceListing


# Register your models here.
admin.site.register(Product)
admin.site.register(Retailer)
admin.site.register(PriceListing)
