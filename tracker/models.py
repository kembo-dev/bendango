from django.core.exceptions import ValidationError
from django.db import models


class Retailer(models.Model):
    """Boutique ou site e-commerce (ex: Amazon, Fnac, Cdiscount)"""
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['base_url'])]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Produit générique à comparer"""
    name = models.CharField(max_length=255)
    sku_or_ean = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['sku_or_ean'])]

    def __str__(self):
        return self.name

class PriceListing(models.Model):
    """Relevé de prix d'un produit sur un site spécifique à un instant T"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='listings')
    retailer = models.ForeignKey(Retailer, on_delete=models.CASCADE)
    url = models.URLField(max_length=500)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    in_stock = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'retailer', 'url'],
                name='unique_listing_per_product_retailer_url',
            )
        ]
        indexes = [models.Index(fields=['product', 'retailer', 'price'])]

    def clean(self):
        super().clean()
        if self.price is None or self.price <= 0:
            raise ValidationError({'price': 'Le prix doit être strictement positif.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.retailer.name}: {self.price} {self.currency}"