from django.core.exceptions import ValidationError
from django.db import models

from tracker.currency import convert_price, normalize_currency


class Retailer(models.Model):
    """Boutique ou site e-commerce."""
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['base_url'])]

    def __str__(self):
        return self.name


class Product(models.Model):
    """Produit canonique utilisé pour rapprocher les offres de plusieurs marchands."""
    name = models.CharField(max_length=255)
    sku_or_ean = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    brand = models.CharField(max_length=120, blank=True, default='')
    model = models.CharField(max_length=160, blank=True, default='')
    category = models.CharField(max_length=120, blank=True, default='')
    image_url = models.URLField(max_length=800, blank=True, default='')
    attributes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['sku_or_ean']),
            models.Index(fields=['brand', 'model']),
        ]

    def __str__(self):
        return self.name


class PriceListing(models.Model):
    """Dernier état connu d'une offre chez un marchand."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='listings')
    retailer = models.ForeignKey(Retailer, on_delete=models.CASCADE)
    url = models.URLField(max_length=500)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    normalized_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    normalized_currency = models.CharField(max_length=10, default='USD')
    in_stock = models.BooleanField(default=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, default=0.5)
    extraction_source = models.CharField(max_length=30, default='llm')
    is_active = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['normalized_price', 'price']
        constraints = [
            models.UniqueConstraint(
                fields=['product', 'retailer', 'url'],
                name='unique_listing_per_product_retailer_url',
            )
        ]
        indexes = [
            models.Index(fields=['product', 'retailer', 'price']),
            models.Index(fields=['product', 'normalized_price']),
            models.Index(fields=['is_active', 'scraped_at']),
        ]

    def clean(self):
        super().clean()
        if self.price is None or self.price <= 0:
            raise ValidationError({'price': 'Le prix doit être strictement positif.'})
        normalized = normalize_currency(self.currency)
        if normalized is None:
            raise ValidationError({'currency': 'Devise non supportée.'})
        self.currency = normalized
        if self.confidence_score is not None and not (0 <= self.confidence_score <= 1):
            raise ValidationError({'confidence_score': 'Le score doit être compris entre 0 et 1.'})

    def save(self, *args, **kwargs):
        self.currency = normalize_currency(self.currency) or self.currency
        self.normalized_currency = 'USD'
        self.normalized_price = convert_price(self.price, self.currency, self.normalized_currency)
        self.full_clean()
        result = super().save(*args, **kwargs)
        PriceHistory.objects.create(
            listing=self,
            price=self.price,
            currency=self.currency,
            normalized_price=self.normalized_price,
            normalized_currency=self.normalized_currency,
            in_stock=self.in_stock,
        )
        return result

    def __str__(self):
        return f"{self.product.name} - {self.retailer.name}: {self.price} {self.currency}"


class PriceHistory(models.Model):
    """Historique immuable des prix observés pour une offre."""
    listing = models.ForeignKey(PriceListing, on_delete=models.CASCADE, related_name='history')
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10)
    normalized_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    normalized_currency = models.CharField(max_length=10, default='USD')
    in_stock = models.BooleanField(default=True)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-observed_at']
        indexes = [models.Index(fields=['listing', 'observed_at'])]

    def __str__(self):
        return f"{self.listing_id}: {self.price} {self.currency} @ {self.observed_at}"
