from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tracker.product_matching import normalize_product_name


@dataclass
class UnifiedSearchResult:
    key: str
    source_kind: str
    source_label: str
    title: str
    provider: str
    url: str
    image_url: str = ""
    price: Any = None
    currency: str = ""
    price_unit: str = ""
    availability_label: str = ""
    score: float = 0.0
    verified: bool = False
    subtitle: str = ""
    badge: str = ""


def _result_key(source_kind: str, provider: str, title: str, url: str = "") -> str:
    if url:
        return f"{source_kind}:url:{url.strip().lower()}"
    return ":".join([
        source_kind,
        normalize_product_name(provider or ""),
        normalize_product_name(title or ""),
    ])


def build_unified_results(first_party_offers, listings, discovery_sources, *, limit: int = 40):
    results: list[UnifiedSearchResult] = []
    seen_keys: set[str] = set()
    bridged_listing_ids = {
        offer.price_listing_id
        for offer in first_party_offers or []
        if getattr(offer, "price_listing_id", None)
    }

    for offer in first_party_offers or []:
        key = _result_key("bendango", offer.business.business_name, offer.title)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        results.append(UnifiedSearchResult(
            key=key,
            source_kind="bendango",
            source_label="Bendango",
            title=offer.title,
            provider=offer.business.business_name,
            url=f"/offer/{offer.slug}/",
            image_url=offer.display_image_url or "",
            price=offer.price,
            currency=offer.currency,
            price_unit=offer.price_unit,
            availability_label=offer.get_availability_display(),
            score=float(getattr(offer, "search_score", 0.0) or 0.0),
            verified=bool(offer.business.is_verified),
            subtitle=offer.city or offer.business.country or "",
            badge="Publié sur Bendango",
        ))

    for listing in listings or []:
        if listing.pk in bridged_listing_ids:
            continue
        key = _result_key("web", listing.retailer.name, listing.product.name, listing.url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        trust_level = getattr(listing.retailer, "trust_level", "")
        results.append(UnifiedSearchResult(
            key=key,
            source_kind="web",
            source_label="Web marchand",
            title=listing.product.name,
            provider=listing.retailer.name,
            url=listing.url,
            image_url=getattr(listing.product, "image_url", "") or "",
            price=listing.price,
            currency=listing.currency,
            availability_label="En stock" if listing.in_stock else "Rupture",
            score=float(getattr(listing, "offer_quality_score", 0.0) or 0.0),
            verified=trust_level == "verified",
            subtitle=getattr(listing, "get_extraction_source_display", lambda: "")(),
            badge="Marchand vérifié" if trust_level == "verified" else "Offre Web",
        ))

    for source in discovery_sources or []:
        if isinstance(source, dict):
            getter = source.get
        else:
            getter = lambda key, default=None: getattr(source, key, default)
        url = str(getter("url", "") or "")
        title = str(getter("title", "") or "")
        platform = str(getter("platform", "") or "Autre source")
        if not url or not title:
            continue
        key = _result_key("social", platform, title, url)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        source_type = str(getter("source_type", "") or "Autre source")
        results.append(UnifiedSearchResult(
            key=key,
            source_kind="social",
            source_label=source_type,
            title=title,
            provider=platform,
            url=url,
            score=float(getter("relevance_score", 0.0) or 0.0),
            verified=False,
            subtitle=str(getter("snippet", "") or ""),
            badge=source_type,
        ))

    source_priority = {"bendango": 0, "web": 1, "social": 2}
    results.sort(key=lambda item: (
        source_priority.get(item.source_kind, 9),
        -float(item.score or 0.0),
        item.provider.lower(),
        item.title.lower(),
    ))
    return results[:max(1, int(limit))]
