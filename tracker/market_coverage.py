from __future__ import annotations

from urllib.parse import urlparse


def merchant_key(listing) -> str:
    retailer = getattr(listing, "retailer", None)
    if retailer is not None and getattr(retailer, "id", None) is not None:
        return f"retailer:{retailer.id}"
    url = getattr(listing, "url", "") or ""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host or str(id(listing))


def distinct_merchant_count(listings) -> int:
    return len({merchant_key(item) for item in listings if item is not None})


def coverage_summary(listings, target_merchants: int) -> dict:
    merchants = distinct_merchant_count(listings)
    target = max(1, int(target_merchants or 1))
    ratio = min(1.0, merchants / target)
    if merchants >= target:
        level = "good"
        label = "Bonne couverture"
    elif merchants >= max(2, target // 2):
        level = "partial"
        label = "Couverture partielle"
    else:
        level = "limited"
        label = "Couverture limitée"
    return {
        "merchant_count": merchants,
        "target_merchants": target,
        "ratio": ratio,
        "percent": round(ratio * 100),
        "level": level,
        "label": label,
    }
