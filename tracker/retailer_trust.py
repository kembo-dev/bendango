from __future__ import annotations

from decimal import Decimal

from django.db.models import Avg, Count, Q

from tracker.models import PriceListing, Retailer


DEFAULT_TRUST = Decimal("0.6000")
MIN_AUTOMATIC_TRUST = Decimal("0.3500")
MAX_AUTOMATIC_TRUST = Decimal("0.8900")


def _level_for_score(score: Decimal) -> str:
    if score >= Decimal("0.78"):
        return "trusted"
    if score < Decimal("0.50"):
        return "limited"
    return "standard"


def calculate_retailer_trust(retailer: Retailer) -> Decimal:
    """Calculate a conservative trust score from Bendango's own observations.

    Verified retailers are deliberately excluded from automatic promotion or
    demotion. Automatic learning only moves retailers between limited,
    standard and trusted.
    """
    listings = PriceListing.objects.filter(retailer=retailer)
    stats = listings.aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(is_active=True)),
        avg_confidence=Avg("confidence_score", filter=Q(is_active=True)),
        avg_match=Avg("match_score", filter=Q(is_active=True)),
    )

    total = stats["total"] or 0
    if total == 0:
        return DEFAULT_TRUST

    active = stats["active"] or 0
    active_ratio = Decimal(str(active / total))
    confidence = Decimal(str(stats["avg_confidence"] or 0))
    match_score = Decimal(str(stats["avg_match"] or 0))

    # Evidence volume grows slowly: a handful of good pages should help, but a
    # new merchant must not become highly trusted after one successful scrape.
    evidence = min(Decimal("1"), Decimal(str(total)) / Decimal("12"))

    observed_quality = (
        Decimal("0.40") * confidence
        + Decimal("0.35") * match_score
        + Decimal("0.25") * active_ratio
    )

    # Blend observations with a neutral prior. More evidence gives the observed
    # quality more weight, while low-volume merchants stay near the default.
    learned = DEFAULT_TRUST * (Decimal("1") - evidence) + observed_quality * evidence
    return max(MIN_AUTOMATIC_TRUST, min(MAX_AUTOMATIC_TRUST, learned.quantize(Decimal("0.0001"))))


def refresh_retailer_trust(retailer: Retailer, *, save: bool = True) -> Decimal:
    """Refresh trust for a retailer unless it was explicitly verified."""
    if retailer.trust_level == "verified":
        return retailer.trust_score

    score = calculate_retailer_trust(retailer)
    level = _level_for_score(score)
    retailer.trust_score = score
    retailer.trust_level = level
    if save:
        retailer.save(update_fields=["trust_score", "trust_level"])
    return score
