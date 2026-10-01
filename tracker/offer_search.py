from __future__ import annotations

from tracker.markets import GLOBAL_MARKET_CODE, normalize_market_code
from tracker.models import Offer
from tracker.product_matching import match_product, normalize_product_name


def _token_score(query: str, candidate: str) -> float:
    q = set(normalize_product_name(query).split())
    c = set(normalize_product_name(candidate).split())
    if not q or not c:
        return 0.0
    overlap = q & c
    if not overlap:
        return 0.0
    return max(len(overlap) / len(q), len(overlap) / len(c))


def find_matching_offers(query: str, *, market_code: str = GLOBAL_MARKET_CODE, limit: int = 12):
    query = (query or '').strip()
    if not query:
        return []

    market_code = normalize_market_code(market_code)
    qs = Offer.objects.filter(
        is_public=True,
        is_active=True,
        business__is_public=True,
        business__is_active=True,
    ).select_related('business', 'business__category', 'product')

    if market_code != GLOBAL_MARKET_CODE:
        qs = qs.filter(market_code=market_code)

    matched = []
    for offer in qs.order_by('-updated_at')[:250]:
        candidate = ' '.join(
            part for part in (
                offer.title,
                offer.category,
                offer.description,
                offer.business.business_name,
            )
            if part
        )
        if offer.offer_type == Offer.TYPE_PRODUCT:
            result = match_product(query, candidate, threshold=0.60)
            score = result.score
            is_match = result.is_match
        else:
            normalized_query = normalize_product_name(query)
            normalized_candidate = normalize_product_name(candidate)
            score = _token_score(query, candidate)
            is_match = (
                normalized_query in normalized_candidate
                or normalized_candidate in normalized_query
                or score >= 0.55
            )
        if not is_match:
            continue
        offer.search_score = score
        matched.append(offer)

    matched.sort(
        key=lambda offer: (
            -float(getattr(offer, 'search_score', 0)),
            0 if offer.availability == 'available' else 1,
            float(offer.price) if offer.price is not None else float('inf'),
        )
    )
    return matched[:max(1, int(limit))]
