from django.core.exceptions import ValidationError
from django.db import models


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
    """Produit canonique utilisé pour regrouper les offres comparables."""
    name = models.CharField(max_length=255)
    sku_or_ean = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    brand = models.CharField(max_length=100, blank=True, default='')
    model = models.CharField(max_length=150, blank=True, default='')
    category = models.CharField(max_length=100, blank=True, default='')
    image_url = models.URLField(max_length=2048, blank=True, default='')
    attributes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['sku_or_ean'])]

    def __str__(self):
        return self.name


class PriceListing(models.Model):
    """Dernière offre connue d'un produit chez un marchand."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='listings')
    retailer = models.ForeignKey(Retailer, on_delete=models.CASCADE)
    url = models.URLField(max_length=2048)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    normalized_price = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    normalized_currency = models.CharField(max_length=10, default='USD')
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    in_stock = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
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
        if self.confidence_score is not None and not (0 <= self.confidence_score <= 1):
            raise ValidationError({'confidence_score': 'Le score de confiance doit être compris entre 0 et 1.'})

    def save(self, *args, **kwargs):
        from tracker.currency import normalize_to_usd

        previous = None
        if self.pk:
            previous = PriceListing.objects.filter(pk=self.pk).values('price', 'currency', 'in_stock').first()

        self.currency = (self.currency or '').upper()
        self.normalized_currency = 'USD'
        self.normalized_price = normalize_to_usd(self.price, self.currency)
        self.full_clean()
        result = super().save(*args, **kwargs)

        changed = (
            previous is None
            or previous['price'] != self.price
            or previous['currency'] != self.currency
            or previous['in_stock'] != self.in_stock
        )
        if changed:
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
    """Snapshot immuable créé lorsque le prix, la devise ou le stock change."""
    listing = models.ForeignKey(PriceListing, on_delete=models.CASCADE, related_name='history')
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10)
    normalized_price = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    normalized_currency = models.CharField(max_length=10, default='USD')
    in_stock = models.BooleanField(default=True)
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [models.Index(fields=['listing', 'recorded_at'])]

    def __str__(self):
        return f"{self.listing_id}: {self.price} {self.currency} @ {self.recorded_at}"
