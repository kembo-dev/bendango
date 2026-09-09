from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


BLOCKED_HOSTS = {
    "bing.com", "google.com", "duckduckgo.com",
    "studylib.net", "scribd.com", "academia.edu", "gist.github.com",
}

BLOCKED_PATH_MARKERS = (
    "/privacy", "/privacy-policy", "/policies/", "/terms", "/conditions",
    "/forum", "/forums", "/thread", "/threads", "/viewtopic", "/blog/",
    "/category", "/categories", "/categorie", "/cat/", "/collection", "/collections",
    "/search", "/browse/", "/brand/", "/brands/", "/price-list", "/comparatif", "/compare",
    "/meilleur", "/best-", "/wiki", "/dictionary/", "/policies/",
)

PRODUCT_PATH_MARKERS = (
    "/product/", "/products/", "/produit/", "/item/", "/p/", "/dp/", "/article/",
)


FNAC_LISTING_PATTERN = re.compile(r"/(?:n?shi)\d+(?:/[^/?#]+)*/w-\d+(?:/|$)", re.IGNORECASE)


def _host_matches(host: str, blocked: str) -> bool:
    return host == blocked or host.endswith("." + blocked)


def is_low_value_candidate_url(url: str) -> bool:
    """Reject obvious non-product/search/listing pages before network scraping."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    query_params = parse_qs(parsed.query or "")

    if not host:
        return True
    if any(_host_matches(host, blocked) for blocked in BLOCKED_HOSTS):
        return True
    if host == "bing.com" and path.startswith("/aclick"):
        return True
    if any(marker in path for marker in BLOCKED_PATH_MARKERS):
        return True
    if host.endswith("fnac.com") and FNAC_LISTING_PATTERN.search(path):
        return True
    if "amazon." in host and path.rstrip("/") == "/s" and "k" in query_params:
        return True
    if re.search(r"\.(pdf|txt|docx?|epub|xml|csv|zip)$", path):
        return True
    if "?s=" in url.lower() or "search=" in query or "query=" in query:
        return True
    return False


def product_url_score(url: str) -> int:
    """Rank likely product-detail URLs ahead of ambiguous pages."""
    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()
    score = 0
    if any(marker in path for marker in PRODUCT_PATH_MARKERS):
        score += 5
    if re.search(r"\b(\d+)(gb|go|tb|to|ssd|hdd)\b", path):
        score += 2
    if len([part for part in path.split("/") if part]) >= 2:
        score += 1
    if is_low_value_candidate_url(url):
        score -= 10
    return score


def filter_and_rank_candidate_urls(urls):
    """Deduplicate, remove obvious noise and prioritize product-detail candidates."""
    unique = []
    seen = set()
    for url in urls or []:
        if not url or url in seen:
            continue
        seen.add(url)
        if not is_low_value_candidate_url(url):
            unique.append(url)
    return sorted(unique, key=lambda value: product_url_score(value), reverse=True)
