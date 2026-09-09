from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class Retailer(models.Model):
    """Boutique ou site e-commerce."""
    TRUST_LEVELS = [('verified', 'Vérifié'), ('trusted', 'Fiable'), ('standard', 'Standard'), ('limited', 'À confirmer')]
    name = models.CharField(max_length=100, unique=True)
    base_url = models.URLField(unique=True)
    trust_score = models.DecimalField(max_digits=5, decimal_places=4, default=0.60)
    trust_level = models.CharField(max_length=20, choices=TRUST_LEVELS, default='standard')
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [models.Index(fields=['name']), models.Index(fields=['base_url'])]

    def clean(self):
        super().clean()
        if self.trust_score is not None and not (0 <= self.trust_score <= 1):
            raise ValidationError({'trust_score': 'Le score de confiance marchand doit être compris entre 0 et 1.'})

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
    EXTRACTION_SOURCES = [('jsonld', 'JSON-LD'), ('shopify', 'Shopify JSON'), ('meta', 'Meta tags'), ('llm', 'LLM'), ('html', 'HTML fallback'), ('cache', 'Cached listing'), ('unknown', 'Unknown')]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='listings')
    retailer = models.ForeignKey(Retailer, on_delete=models.CASCADE)
    url = models.URLField(max_length=2048)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default='EUR')
    normalized_price = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    normalized_currency = models.CharField(max_length=10, default='USD')
    confidence_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    match_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    extraction_source = models.CharField(max_length=20, choices=EXTRACTION_SOURCES, default='unknown')
    in_stock = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    scraped_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['price']
        constraints = [models.UniqueConstraint(fields=['product', 'retailer', 'url'], name='unique_listing_per_product_retailer_url')]
        indexes = [models.Index(fields=['product', 'retailer', 'price'])]

    def clean(self):
        super().clean()
        if self.price is None or self.price <= 0:
            raise ValidationError({'price': 'Le prix doit être strictement positif.'})
        if self.confidence_score is not None and not (0 <= self.confidence_score <= 1):
            raise ValidationError({'confidence_score': 'Le score de confiance doit être compris entre 0 et 1.'})
        if self.match_score is not None and not (0 <= self.match_score <= 1):
            raise ValidationError({'match_score': 'Le score de matching doit être compris entre 0 et 1.'})

    @staticmethod
    def _is_currency_correction(previous, new_price, new_currency, new_normalized_price):
        """Detect an obvious currency-label repair rather than a real market price change."""
        if not previous or previous['currency'] == new_currency or previous['price'] != new_price:
            return False
        old_normalized = previous.get('normalized_price')
        if old_normalized is None or new_normalized_price is None or old_normalized <= 0 or new_normalized_price <= 0:
            return False
        ratio = max(Decimal(old_normalized), Decimal(new_normalized_price)) / min(Decimal(old_normalized), Decimal(new_normalized_price))
        return ratio >= Decimal('10')

    def _repair_stale_currency_history(self):
        """Repair old snapshots created with a wrong currency label for the same raw amount."""
        if not self.pk or self.normalized_price is None or self.normalized_price <= 0:
            return 0

        repaired = 0
        stale = PriceHistory.objects.filter(listing=self, price=self.price).exclude(currency=self.currency)
        for snapshot in stale:
            if snapshot.normalized_price is None or snapshot.normalized_price <= 0:
                continue
            ratio = max(Decimal(snapshot.normalized_price), Decimal(self.normalized_price)) / min(Decimal(snapshot.normalized_price), Decimal(self.normalized_price))
            if ratio < Decimal('10'):
                continue
            PriceHistory.objects.filter(pk=snapshot.pk).update(
                currency=self.currency,
                normalized_price=self.normalized_price,
                normalized_currency=self.normalized_currency,
            )
            repaired += 1
        return repaired

    def save(self, *args, **kwargs):
        from tracker.currency import normalize_to_usd
        previous = PriceListing.objects.filter(pk=self.pk).values('price', 'currency', 'normalized_price', 'in_stock').first() if self.pk else None
        self.currency = (self.currency or '').upper()
        self.normalized_currency = 'USD'
        self.normalized_price = normalize_to_usd(self.price, self.currency)
        self.full_clean()

        currency_correction = self._is_currency_correction(previous, self.price, self.currency, self.normalized_price)
        result = super().save(*args, **kwargs)

        if currency_correction:
            PriceHistory.objects.filter(
                listing=self,
                price=self.price,
                currency=previous['currency'],
            ).update(
                currency=self.currency,
                normalized_price=self.normalized_price,
                normalized_currency=self.normalized_currency,
            )

        # Always repair stale snapshots as well. This matters when a previous request
        # already corrected the current listing currency but left old history behind.
        self._repair_stale_currency_history()

        changed = previous is None or previous['price'] != self.price or previous['currency'] != self.currency or previous['in_stock'] != self.in_stock
        if currency_correction:
            if not PriceHistory.objects.filter(
                listing=self,
                price=self.price,
                currency=self.currency,
                in_stock=self.in_stock,
            ).exists():
                PriceHistory.objects.create(
                    listing=self,
                    price=self.price,
                    currency=self.currency,
                    normalized_price=self.normalized_price,
                    normalized_currency=self.normalized_currency,
                    in_stock=self.in_stock,
                )
        elif changed:
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


class SearchDiagnostic(models.Model):
    """Résumé technique d'une recherche pour mesurer et améliorer la couverture."""
    query = models.CharField(max_length=255, db_index=True)
    site_filter = models.CharField(max_length=255, default='all')
    search_terms_count = models.PositiveIntegerField(default=0)
    candidate_urls_count = models.PositiveIntegerField(default=0)
    processed_urls_count = models.PositiveIntegerField(default=0)
    fallback_urls_count = models.PositiveIntegerField(default=0)
    offers_count = models.PositiveIntegerField(default=0)
    merchant_count = models.PositiveIntegerField(default=0)
    target_merchants = models.PositiveIntegerField(default=1)
    coverage_ratio = models.FloatField(default=0)
    rejection_reasons = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['created_at', 'coverage_ratio'])]

    def __str__(self):
        return f"{self.query}: {self.merchant_count}/{self.target_merchants} marchands"
