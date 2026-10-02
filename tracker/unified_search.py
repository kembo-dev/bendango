from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tracker.product_matching import match_product, normalize_product_name


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
    item_type: str = ""
    canonical_group: str = ""
    group_size: int = 1
    ranking_score: float = 0.0
    promoted: bool = False


def _result_key(source_kind: str, provider: str, title: str, url: str = "") -> str:
    if url:
        return f"{source_kind}:url:{url.strip().lower()}"
    return ":".join([
        source_kind,
        normalize_product_name(provider or ""),
        normalize_product_name(title or ""),
    ])


def _non_product_ranking_score(offer) -> float:
    score = float(getattr(offer, "search_score", 0.0) or 0.0)
    score *= 0.72
    if getattr(offer.business, "is_verified", False):
        score += 0.10
    if getattr(offer, "availability", "") == "available":
        score += 0.08
    elif getattr(offer, "availability", "") == "on_request":
        score += 0.03
    if getattr(offer, "price", None) is not None:
        score += 0.03
    if getattr(offer, "display_image_url", ""):
        score += 0.02
    if getattr(offer, "whatsapp", "") or getattr(offer.business, "whatsapp", ""):
        score += 0.02
    if getattr(offer, "city", ""):
        score += 0.01

    offer_type = getattr(offer, "offer_type", "")
    price_unit = (getattr(offer, "price_unit", "") or "").lower()
    if offer_type == "accommodation" and price_unit in {"nuit", "night", "jour", "day"}:
        score += 0.02
    elif offer_type == "service" and getattr(offer, "contact_method", "") in {"whatsapp", "phone"}:
        score += 0.02
    elif offer_type in {"restaurant", "health"} and getattr(offer, "availability", "") == "available":
        score += 0.02
    elif offer_type in {"transport", "real_estate"} and getattr(offer, "city", ""):
        score += 0.02

    return round(min(score, 1.0), 4)


def _assign_canonical_product_groups(results: list[UnifiedSearchResult]) -> None:
    groups: list[dict] = []
    for item in results:
        if item.item_type != "product" or item.source_kind not in {"bendango", "web"}:
            continue
        matched_group = None
        for group in groups:
            # Canonical grouping can tolerate harmless title differences such as
            # omitted brand/network labels or an added "RAM" token. The product
            # matcher still rejects real capacity/model/variant conflicts before
            # applying this lower grouping threshold.
            match = match_product(group["title"], item.title, threshold=0.60)
            if match.is_match:
                matched_group = group
                break
        if matched_group is None:
            normalized = normalize_product_name(item.title)
            matched_group = {
                "id": f"product-{len(groups) + 1}-{normalized[:48].replace(' ', '-')}",
                "title": item.title,
                "items": [],
            }
            groups.append(matched_group)
        matched_group["items"].append(item)

    for group in groups:
        size = len(group["items"])
        for item in group["items"]:
            item.canonical_group = group["id"]
            item.group_size = size


def build_unified_results(
    first_party_offers,
    listings,
    discovery_sources,
    *,
    source_filter: str = "",
    offer_type: str = "",
    city: str = "",
    business_category: str = "",
    limit: int = 40,
):
    results: list[UnifiedSearchResult] = []
    seen_keys: set[str] = set()
    bridged_listing_ids = {
        offer.price_listing_id
        for offer in first_party_offers or []
        if getattr(offer, "price_listing_id", None)
    }

    normalized_city = normalize_product_name(city)
    for offer in first_party_offers or []:
        if source_filter and source_filter != "bendango":
            continue
        if offer_type and offer.offer_type != offer_type:
            continue
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
            item_type=offer.offer_type,
            ranking_score=(
                min(
                    1.0,
                    float(getattr(offer, "search_score", 0.0) or 0.0)
                    + (0.08 * float(getattr(offer, "locality_score", 0.0) or 0.0))
                    + (0.15 if offer.is_boosted else 0.0)
                )
                if offer.offer_type == "product"
                else min(
                    1.0,
                    _non_product_ranking_score(offer)
                    + (0.10 * float(getattr(offer, "locality_score", 0.0) or 0.0))
                )
            ),
            promoted=bool(offer.offer_type == "product" and offer.is_boosted),
        ))

    for listing in listings or []:
        if business_category:
            continue
        if source_filter and source_filter != "web":
            continue
        if offer_type and offer_type != "product":
            continue
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
            item_type="product",
            ranking_score=float(getattr(listing, "offer_quality_score", 0.0) or 0.0),
        ))

    for source in discovery_sources or []:
        if business_category:
            continue
        if source_filter and source_filter != "social":
            continue
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
            item_type="discovery",
            ranking_score=float(getter("relevance_score", 0.0) or 0.0),
        ))

    _assign_canonical_product_groups(results)

    source_priority = {"bendango": 0, "web": 1, "social": 2}
    results.sort(key=lambda item: (
        source_priority.get(item.source_kind, 9),
        0 if item.promoted else 1,
        -float(item.ranking_score or item.score or 0.0),
        item.provider.lower(),
        item.title.lower(),
    ))
    return results[:max(1, int(limit))]
