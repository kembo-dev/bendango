from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse


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

EDITORIAL_HOST_MARKERS = (
    "forum", "wiki", "blog", "news", "review", "reviews", "tabs", "tablature",
    "apprendre", "learn", "academy", "directory", "annuaire",
)

EDITORIAL_PATH_MARKERS = (
    "/guide/", "/guides/", "/conseil/", "/conseils/", "/actualite/", "/actualites/",
    "/news/", "/review/", "/reviews/", "/test/", "/tests/", "/tutorial/", "/tutorials/",
    "/cours/", "/lesson/", "/lessons/", "/tabs/", "/tablature/", "/chords/",
)

SHOPPING_PATH_HINTS = (
    "shop", "store", "boutique", "market", "mart", "vente", "acheter", "buy", "prix", "price",
)

FNAC_LISTING_PATTERN = re.compile(r"/(?:n?shi)\d+(?:/[^/?#]+)*/w-\d+(?:/|$)", re.IGNORECASE)


def _host_matches(host: str, blocked: str) -> bool:
    return host == blocked or host.endswith("." + blocked)


def _query_tokens(query: str | None):
    return [token.lower() for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", query or "") if len(token) > 1]


def _is_broad_query(query: str | None) -> bool:
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", query or "")
    meaningful = [token for token in tokens if len(token) > 1]
    has_model_signal = any(any(char.isdigit() for char in token) for token in tokens)
    return bool(meaningful) and len(meaningful) <= 2 and not has_model_signal


def _has_product_path(path: str) -> bool:
    return any(marker in path for marker in PRODUCT_PATH_MARKERS)


def _looks_editorial(host: str, path: str) -> bool:
    return any(marker in host for marker in EDITORIAL_HOST_MARKERS) or any(marker in path for marker in EDITORIAL_PATH_MARKERS)


def _looks_like_shopping_url(host: str, path: str) -> bool:
    combined = f"{host} {path}"
    return _has_product_path(path) or any(hint in combined for hint in SHOPPING_PATH_HINTS)


def is_low_value_candidate_url(url: str, query: str | None = None) -> bool:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = unquote(parsed.path or "").lower()
    query_string = (parsed.query or "").lower()
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
    if "amazon." in host and path.rstrip("/").endswith("/s") and "k" in query_params:
        return True
    if re.search(r"\.(pdf|txt|docx?|epub|xml|csv|zip)$", path):
        return True
    if "?s=" in url.lower() or "search=" in query_string or "query=" in query_string:
        return True

    if query and _is_broad_query(query):
        # Generic searches attract editorial pages very easily. Require stronger
        # commerce evidence before they enter the expensive scrape queue.
        if _looks_editorial(host, path) and not _has_product_path(path):
            return True
        segments = [segment for segment in path.split("/") if segment]
        if len(segments) <= 1 and not _looks_like_shopping_url(host, path):
            return True

    return False


def product_url_score(url: str, query: str | None = None) -> int:
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = unquote(parsed.path or "").lower()
    score = 0
    if _has_product_path(path):
        score += 5
    if re.search(r"\b(\d+)(gb|go|tb|to|ssd|hdd)\b", path):
        score += 2
    if len([part for part in path.split("/") if part]) >= 2:
        score += 1
    if _looks_like_shopping_url(host, path):
        score += 1
    if query:
        haystack = f"{host} {path}".replace("-", " ").replace("_", " ")
        overlap = sum(1 for token in _query_tokens(query) if token in haystack)
        score += min(overlap, 3)
    if is_low_value_candidate_url(url, query=query):
        score -= 10
    return score


def filter_and_rank_candidate_urls(urls, health_score_func=None, query: str | None = None):
    """Filter obvious noise and rank product-like URLs, optionally using domain health."""
    unique = []
    seen = set()
    for url in urls or []:
        if not url or url in seen:
            continue
        seen.add(url)
        if not is_low_value_candidate_url(url, query=query):
            unique.append(url)

    if health_score_func is None:
        return sorted(unique, key=lambda value: product_url_score(value, query=query), reverse=True)

    return sorted(
        unique,
        key=lambda value: (product_url_score(value, query=query), health_score_func(value)),
        reverse=True,
    )
