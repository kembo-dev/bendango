from __future__ import annotations

import re
from urllib.parse import urlparse


GENERIC_SUBDOMAINS = {
    "www", "shop", "store", "boutique", "m", "mobile",
    "fr", "en", "de", "es", "it", "nl", "pt", "be", "ca", "us", "uk",
}

COMMON_SECOND_LEVEL_SUFFIXES = {
    "co", "com", "net", "org", "ac", "gov",
}


def _host_from_listing(listing) -> str:
    retailer = getattr(listing, "retailer", None)
    base_url = getattr(retailer, "base_url", "") if retailer is not None else ""
    url = base_url or getattr(listing, "url", "") or ""
    return urlparse(url).netloc.lower().removeprefix("www.").split(":", 1)[0]


def _merchant_brand_from_host(host: str) -> str:
    """Return a stable storefront identity across country/language domains.

    Examples:
      fr.knivesandtools.be -> knivesandtools
      knivesandtools.fr    -> knivesandtools
      amazon.co.uk         -> amazon

    This deliberately normalizes only host structure; it does not merge unrelated
    retailers based on fuzzy display-name similarity.
    """
    labels = [label for label in (host or "").split(".") if label]
    if not labels:
        return ""

    while len(labels) > 2 and labels[0] in GENERIC_SUBDOMAINS:
        labels.pop(0)

    if len(labels) >= 3 and labels[-2] in COMMON_SECOND_LEVEL_SUFFIXES and len(labels[-1]) == 2:
        candidate = labels[-3]
    elif len(labels) >= 2:
        candidate = labels[-2]
    else:
        candidate = labels[0]

    normalized = re.sub(r"[^a-z0-9]+", "", candidate.lower())
    return normalized or host


def merchant_key(listing) -> str:
    host = _host_from_listing(listing)
    brand = _merchant_brand_from_host(host)
    if brand:
        return f"merchant:{brand}"

    retailer = getattr(listing, "retailer", None)
    if retailer is not None and getattr(retailer, "id", None) is not None:
        return f"retailer:{retailer.id}"
    return str(id(listing))


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
