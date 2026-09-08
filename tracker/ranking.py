from __future__ import annotations


def offer_quality_score(listing) -> float:
    """Blend merchant trust, extraction confidence and product matching."""
    retailer_trust = float(getattr(listing.retailer, "trust_score", 0.60) or 0.60)
    confidence = float(getattr(listing, "confidence_score", 0) or 0)
    match_score = float(getattr(listing, "match_score", 0) or 0)
    score = (0.40 * retailer_trust) + (0.35 * confidence) + (0.25 * match_score)
    return round(max(0.0, min(score, 1.0)), 4)


def attach_offer_quality(listings):
    for listing in listings:
        listing.offer_quality_score = offer_quality_score(listing)
    return listings


def offer_sort_key(listing):
    """Stock first, then quality, then normalized price."""
    quality = getattr(listing, "offer_quality_score", offer_quality_score(listing))
    normalized = getattr(listing, "normalized_price", None)
    price = float(normalized if normalized is not None else listing.price)
    return (0 if listing.in_stock else 1, -quality, price)
