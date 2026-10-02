import uuid
from datetime import timedelta
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