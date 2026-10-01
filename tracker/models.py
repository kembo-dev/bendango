import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


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
    EXTRACTION_SOURCES = [('jsonld', 'JSON-LD'), ('microdata', 'Schema.org microdata'), ('shopify', 'Shopify JSON'), ('meta', 'Meta tags'), ('llm', 'LLM'), ('html', 'HTML fallback'), ('cache', 'Cached listing'), ('unknown', 'Unknown')]
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
        if not previous or previous['currency'] == new_currency or previous['price'] != new_price:
            return False
        old_normalized = previous.get('normalized_price')
        if old_normalized is None or new_normalized_price is None or old_normalized <= 0 or new_normalized_price <= 0:
            return False
        ratio = max(Decimal(old_normalized), Decimal(new_normalized_price)) / min(Decimal(old_normalized), Decimal(new_normalized_price))
        return ratio >= Decimal('10')

    def _repair_stale_currency_history(self):
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
            PriceHistory.objects.filter(pk=snapshot.pk).update(currency=self.currency, normalized_price=self.normalized_price, normalized_currency=self.normalized_currency)
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
            PriceHistory.objects.filter(listing=self, price=self.price, currency=previous['currency']).update(currency=self.currency, normalized_price=self.normalized_price, normalized_currency=self.normalized_currency)
        self._repair_stale_currency_history()
        changed = previous is None or previous['price'] != self.price or previous['currency'] != self.currency or previous['in_stock'] != self.in_stock
        if currency_correction:
            if not PriceHistory.objects.filter(listing=self, price=self.price, currency=self.currency, in_stock=self.in_stock).exists():
                PriceHistory.objects.create(listing=self, price=self.price, currency=self.currency, normalized_price=self.normalized_price, normalized_currency=self.normalized_currency, in_stock=self.in_stock)
        elif changed:
            PriceHistory.objects.create(listing=self, price=self.price, currency=self.currency, normalized_price=self.normalized_price, normalized_currency=self.normalized_currency, in_stock=self.in_stock)
        return result

    def __str__(self):
        return f"{self.product.name} - {self.retailer.name}: {self.price} {self.currency}"


class PriceHistory(models.Model):
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


class SearchRun(models.Model):
    """One user search execution, including asynchronous discovery state."""
    STATUS_QUEUED = 'queued'
    STATUS_DISCOVERING = 'discovering'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_QUEUED, 'Queued'),
        (STATUS_DISCOVERING, 'Discovering'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='search_runs',
    )
    query = models.CharField(max_length=255, db_index=True)
    site_filter = models.CharField(max_length=255, default='all')
    target_merchants = models.PositiveIntegerField(default=1)
    model_name = models.CharField(max_length=255, blank=True, default='')
    market_code = models.CharField(max_length=8, default='CD', db_index=True)
    market_currency = models.CharField(max_length=8, default='CDF')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_QUEUED, db_index=True)
    discovery_sources = models.JSONField(default=list, blank=True)
    discovery_error = models.TextField(blank=True, default='')
    discovery_started_at = models.DateTimeField(blank=True, null=True)
    discovery_finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['query', 'created_at'], name='tracker_run_query_created_idx'),
            models.Index(fields=['status', 'created_at'], name='tracker_run_status_created_idx'),
        ]

    def __str__(self):
        return f"{self.query} [{self.id}]"


class ScrapeJob(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_RETRY = 'retry'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_RETRY, 'Retry'),
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]

    search_run = models.ForeignKey(SearchRun, on_delete=models.SET_NULL, blank=True, null=True, related_name='jobs')
    url = models.URLField(max_length=2048, db_index=True)
    query = models.CharField(max_length=255, blank=True, default='')
    model_name = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    last_error = models.TextField(blank=True, default='')
    fetch_status = models.CharField(max_length=32, blank=True, default='')
    http_status = models.PositiveIntegerField(blank=True, null=True)
    duration_ms = models.PositiveIntegerField(default=0)
    from_cache = models.BooleanField(default=False)
    listing = models.ForeignKey(PriceListing, on_delete=models.SET_NULL, blank=True, null=True, related_name='scrape_jobs')
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['available_at', 'created_at']
        indexes = [
            models.Index(fields=['status', 'available_at'], name='tracker_scr_status_avail_idx'),
            models.Index(fields=['url', 'status'], name='tracker_scr_url_status_idx'),
            models.Index(fields=['search_run', 'status'], name='tracker_scr_run_status_idx'),
        ]

    def __str__(self):
        return f"{self.status}: {self.url}"



class BusinessCategory(models.Model):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140] or f"category-{self.pk or 'new'}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class BusinessProfile(models.Model):
    """Universal Bendango business profile for stores, sellers, services, hotels and more."""

    VERIFY_UNVERIFIED = 'unverified'
    VERIFY_IDENTITY = 'identity'
    VERIFY_BUSINESS = 'business'
    VERIFY_PARTNER = 'partner'
    VERIFICATION_LEVELS = [
        (VERIFY_UNVERIFIED, 'Non vérifié'),
        (VERIFY_IDENTITY, 'Identité vérifiée'),
        (VERIFY_BUSINESS, 'Business vérifié'),
        (VERIFY_PARTNER, 'Partenaire Bendango'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='business_profile',
    )
    business_name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    business_type = models.CharField(max_length=120, blank=True, default='')
    category = models.ForeignKey(
        BusinessCategory,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='businesses',
    )
    website = models.URLField(max_length=2048, blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')
    whatsapp = models.CharField(max_length=40, blank=True, default='')
    public_email = models.EmailField(blank=True, default='')
    facebook_url = models.URLField(max_length=2048, blank=True, default='')
    instagram_url = models.URLField(max_length=2048, blank=True, default='')
    tiktok_url = models.URLField(max_length=2048, blank=True, default='')
    country = models.CharField(max_length=100, blank=True, default='')
    city = models.CharField(max_length=120, blank=True, default='')
    market_code = models.CharField(max_length=8, default='CD', db_index=True)
    address = models.CharField(max_length=255, blank=True, default='')
    logo_url = models.URLField(max_length=2048, blank=True, default='')
    cover_image_url = models.URLField(max_length=2048, blank=True, default='')
    opening_hours = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True, default='')
    verification_level = models.CharField(
        max_length=16,
        choices=VERIFICATION_LEVELS,
        default=VERIFY_BUSINESS,
        db_index=True,
    )
    phone_verified = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    address_verified = models.BooleanField(default=False)
    documents_verified = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=True, db_index=True)
    is_public = models.BooleanField(default=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    approved_request = models.OneToOneField(
        'BusinessAccountRequest',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='activated_profile',
    )
    retailer = models.OneToOneField(
        Retailer,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='business_profile',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['business_name']
        indexes = [
            models.Index(fields=['business_name'], name='tracker_biz_name_idx'),
            models.Index(fields=['slug'], name='tracker_biz_slug_idx'),
            models.Index(fields=['is_verified'], name='tracker_biz_verified_idx'),
            models.Index(fields=['market_code', 'city'], name='tracker_biz_market_city_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.business_name)[:190] or 'business'
            candidate = base
            suffix = 2
            while BusinessProfile.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:180]}-{suffix}"
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def ensure_retailer(self):
        if self.retailer_id:
            return self.retailer
        base_url = (self.website or '').strip()
        if not base_url:
            base_url = f"https://bendango.local/business/{self.pk}/"
        retailer_name = self.business_name[:100]
        if Retailer.objects.filter(name=retailer_name).exclude(base_url=base_url).exists():
            retailer_name = f"{self.business_name[:80]} #{self.pk}"[:100]
        retailer, _ = Retailer.objects.get_or_create(
            base_url=base_url,
            defaults={
                'name': retailer_name,
                'trust_score': Decimal('0.85'),
                'trust_level': 'verified',
                'is_active': True,
            },
        )
        changed = False
        if retailer.name != retailer_name:
            retailer.name = retailer_name
            changed = True
        if retailer.trust_level != 'verified':
            retailer.trust_level = 'verified'
            changed = True
        if not retailer.is_active:
            retailer.is_active = True
            changed = True
        if changed:
            retailer.save()
        self.retailer = retailer
        self.save(update_fields=['retailer'])
        return retailer

    def __str__(self):
        return self.business_name


class Offer(models.Model):
    TYPE_PRODUCT = 'product'
    TYPE_SERVICE = 'service'
    TYPE_ACCOMMODATION = 'accommodation'
    TYPE_RESTAURANT = 'restaurant'
    TYPE_HEALTH = 'health'
    TYPE_TRANSPORT = 'transport'
    TYPE_REAL_ESTATE = 'real_estate'
    TYPE_OTHER = 'other'
    OFFER_TYPES = [
        (TYPE_PRODUCT, 'Produit'),
        (TYPE_SERVICE, 'Service'),
        (TYPE_ACCOMMODATION, 'Hôtel / logement'),
        (TYPE_RESTAURANT, 'Restaurant / menu'),
        (TYPE_HEALTH, 'Santé / pharmacie'),
        (TYPE_TRANSPORT, 'Transport'),
        (TYPE_REAL_ESTATE, 'Immobilier'),
        (TYPE_OTHER, 'Autre'),
    ]
    AVAILABILITY_CHOICES = [
        ('available', 'Disponible'),
        ('unavailable', 'Indisponible'),
        ('on_request', 'Sur demande'),
    ]
    CONTACT_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('phone', 'Téléphone'),
        ('external', 'Lien externe'),
        ('business', 'Contacter le business'),
    ]

    business = models.ForeignKey(BusinessProfile, on_delete=models.CASCADE, related_name='offers')
    offer_type = models.CharField(max_length=24, choices=OFFER_TYPES, default=TYPE_PRODUCT, db_index=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=240, unique=True, blank=True)
    description = models.TextField(blank=True, default='')
    category = models.CharField(max_length=120, blank=True, default='')
    price = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=10, blank=True, default='USD')
    price_unit = models.CharField(max_length=60, blank=True, default='')
    availability = models.CharField(max_length=16, choices=AVAILABILITY_CHOICES, default='available', db_index=True)
    primary_image_url = models.URLField(max_length=2048, blank=True, default='')
    external_url = models.URLField(max_length=2048, blank=True, default='')
    whatsapp = models.CharField(max_length=40, blank=True, default='')
    contact_method = models.CharField(max_length=16, choices=CONTACT_CHOICES, default='business')
    market_code = models.CharField(max_length=8, default='CD', db_index=True)
    city = models.CharField(max_length=120, blank=True, default='')
    attributes = models.JSONField(default=dict, blank=True)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, blank=True, null=True, related_name='business_offers')
    price_listing = models.OneToOneField(PriceListing, on_delete=models.SET_NULL, blank=True, null=True, related_name='business_offer')
    is_public = models.BooleanField(default=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-created_at']
        indexes = [
            models.Index(fields=['business', 'is_active'], name='tracker_offer_biz_active_idx'),
            models.Index(fields=['offer_type', 'market_code'], name='tracker_offer_type_market_idx'),
            models.Index(fields=['title'], name='tracker_offer_title_idx'),
        ]

    def save(self, *args, **kwargs):
        if self.business_id:
            if not self.market_code:
                self.market_code = self.business.market_code
            if not self.city:
                self.city = self.business.city
            if not self.whatsapp:
                self.whatsapp = self.business.whatsapp
        if not self.slug:
            base = slugify(f"{self.business.business_name}-{self.title}")[:210] or 'offer'
            candidate = base
            suffix = 2
            while Offer.objects.exclude(pk=self.pk).filter(slug=candidate).exists():
                candidate = f"{base[:200]}-{suffix}"
                suffix += 1
            self.slug = candidate
        self.currency = (self.currency or '').upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.business.business_name}: {self.title}"


class BusinessAccountRequest(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_APPROVED, 'Approuvée'),
        (STATUS_REJECTED, 'Refusée'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='business_account_requests',
    )
    business_name = models.CharField(max_length=180)
    business_type = models.CharField(max_length=120, blank=True, default='')
    website = models.URLField(max_length=2048, blank=True, default='')
    phone = models.CharField(max_length=40, blank=True, default='')
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    admin_note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at'], name='tracker_biz_user_created_idx'),
            models.Index(fields=['status', 'created_at'], name='tracker_biz_status_created_idx'),
        ]

    def activate_profile(self):
        """Create or refresh the user's professional profile from this request."""
        if self.status != self.STATUS_APPROVED:
            return None
        profile, _ = BusinessProfile.objects.get_or_create(
            user=self.user,
            defaults={
                'business_name': self.business_name,
                'business_type': self.business_type,
                'website': self.website,
                'phone': self.phone,
                'description': self.description,
                'is_verified': True,
                'approved_request': self,
            },
        )
        changed = False
        source_fields = {
            'business_name': self.business_name,
            'business_type': self.business_type,
            'website': self.website,
            'phone': self.phone,
            'description': self.description,
        }
        for field, value in source_fields.items():
            if not getattr(profile, field):
                setattr(profile, field, value)
                changed = True
        if not profile.is_verified:
            profile.is_verified = True
            changed = True
        if profile.approved_request_id != self.pk:
            profile.approved_request = self
            changed = True
        if changed:
            profile.save()
        return profile

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        if self.status == self.STATUS_APPROVED:
            self.activate_profile()
        elif self.status == self.STATUS_REJECTED:
            BusinessProfile.objects.filter(
                user=self.user,
                approved_request=self,
            ).update(is_verified=False)
        return result

    def __str__(self):
        return f"{self.business_name} - {self.user}"
