from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from tracker.candidate_filter import is_low_value_candidate_url
from tracker.markets import normalize_market_code
from tracker.models import PriceListing, ScrapeJob
from tracker.product_matching import match_product


def find_fresh_cached_listings(
    query: str,
    *,
    site_hosts: list[str] | None = None,
    market_code: str | None = None,
    max_age_minutes: int | None = None,
    minimum_confidence: float | None = None,
) -> list[PriceListing]:
    """Return recent active offers that confidently match a product query.

    Cached listings must still satisfy today's merchant-source policy. This is
    important when a domain was accepted historically and is later classified
    as comparison/editorial: old rows remain useful for audit/history but must
    not silently count as a merchant in new SearchRuns.
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

    if market_code:
        market_code = normalize_market_code(market_code)
        validated_listing_ids = ScrapeJob.objects.filter(
            status=ScrapeJob.STATUS_SUCCESS,
            listing__isnull=False,
            search_run__isnull=False,
            search_run__market_code=market_code,
        ).values_list("listing_id", flat=True)
        queryset = queryset.filter(pk__in=validated_listing_ids)

    normalized_hosts = {
        host.lower().removeprefix("www.")
        for host in (site_hosts or [])
        if host
    }

    matches: list[PriceListing] = []
    for listing in queryset:
        if is_low_value_candidate_url(listing.url, query=query):
            continue
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
