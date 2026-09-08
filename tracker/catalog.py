from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from tracker.models import PriceListing
from tracker.product_matching import match_product


def find_fresh_cached_listings(
    query: str,
    *,
    site_hosts: list[str] | None = None,
    max_age_minutes: int | None = None,
    minimum_confidence: float | None = None,
) -> list[PriceListing]:
    """Return recent active offers that confidently match a product query.

    The cache is conservative: only fresh, active and sufficiently confident
    listings are returned. Matching is re-evaluated against the current query
    so old catalog rows cannot bypass Product Matching V2.
    """
    if not query or not query.strip():
        return []

    if max_age_minutes is None:
        max_age_minutes = int(getattr(settings, "CATALOG_CACHE_MINUTES", 60))
    if minimum_confidence is None:
        minimum_confidence = float(getattr(settings, "CATALOG_CACHE_MIN_CONFIDENCE", 0.70))

    cutoff = timezone.now() - timedelta(minutes=max(0, max_age_minutes))
    queryset = (
        PriceListing.objects.select_related("product", "retailer")
        .filter(
            is_active=True,
            scraped_at__gte=cutoff,
            confidence_score__gte=minimum_confidence,
        )
    )

    normalized_hosts = {
        host.lower().removeprefix("www.")
        for host in (site_hosts or [])
        if host
    }

    matches: list[PriceListing] = []
    for listing in queryset:
        if normalized_hosts:
            retailer_host = (
                listing.retailer.base_url.lower()
                .replace("https://", "")
                .replace("http://", "")
                .split("/", 1)[0]
                .removeprefix("www.")
            )
            if retailer_host not in normalized_hosts:
                continue

        result = match_product(query, listing.product.name)
        if not result.is_match:
            continue

        # Keep the current matching quality visible even for cache hits.
        listing.match_score = result.score
        matches.append(listing)

    matches.sort(
        key=lambda item: (
            0 if item.in_stock else 1,
            float(item.normalized_price if item.normalized_price is not None else item.price),
            -float(item.confidence_score or 0),
        )
    )
    return matches
