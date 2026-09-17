from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse


BLOCKED_HOSTS = {
    "bing.com", "google.com", "duckduckgo.com",
    "studylib.net", "scribd.com", "academia.edu", "gist.github.com",
}

DISCOVERY_ONLY_HOSTS = {
    "facebook.com", "fb.com", "instagram.com", "tiktok.com",
    "youtube.com", "youtu.be", "reddit.com", "pinterest.com",
    "x.com", "twitter.com", "linkedin.com",
}

COMPARISON_EDITORIAL_HOSTS = {
    "lesnumeriques.com",
    "kimovil.com",
    "idealo.fr",
    "123comparer.fr",
    "accio.com",
    "chooseyourmobile.com",
    "kalvo.com",
    "mobolist.net",
    "smartprix.com",
    "techspecs.info",
    "gsmarena.com",
    "versus.com",
}

BLOCKED_PATH_MARKERS = (
    "/privacy", "/privacy-policy", "/policies/", "/terms", "/conditions",
    "/forum", "/forums", "/thread", "/threads", "/viewtopic", "/blog/",
    "/category", "/categories", "/categorie", "/cat/", "/collection", "/collections",
    "/search", "/browse/", "/brand/", "/brands/", "/price-list", "/comparatif", "/compare",
    "/meilleur", "/best-", "/wiki", "/dictionary/", "/policies/",
    "/recommandation/", "/recommandations/", "/recommendation/", "/recommendations/",
)

PRODUCT_PATH_MARKERS = (
    "/product/", "/products/", "/produit/", "/produits/", "/item/", "/p/", "/dp/", "/article/",
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

AMBIGUOUS_PATH_MARKERS = (
    "/catalog/", "/catalogue/", "/listing/", "/list/", "/offers/", "/offres/", "/deals/",
    "/promo/", "/promotions/", "/tag/", "/tags/", "/results/", "/resultats/",
)

GENERIC_PATH_WORDS = {
    "home", "accueil", "shop", "store", "boutique", "catalog", "catalogue", "market",
    "products", "produits", "product", "produit", "offers", "offres", "deals", "promo",
}

FNAC_LISTING_PATTERN = re.compile(r"/(?:n?shi)\d+(?:/[^/?#]+)*/w-\d+(?:/|$)", re.IGNORECASE)


def _host_matches(host: str, blocked: str) -> bool:
    return host == blocked or host.endswith("." + blocked)


def _is_discovery_only_host(host: str) -> bool:
    return any(_host_matches(host, candidate) for candidate in DISCOVERY_ONLY_HOSTS)


def _is_comparison_or_editorial_host(host: str) -> bool:
    return any(_host_matches(host, candidate) for candidate in COMPARISON_EDITORIAL_HOSTS)


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
    return (
        _is_comparison_or_editorial_host(host)
        or any(marker in host for marker in EDITORIAL_HOST_MARKERS)
        or any(marker in path for marker in EDITORIAL_PATH_MARKERS)
    )


def _looks_like_shopping_url(host: str, path: str) -> bool:
    combined = f"{host} {path}"
    return _has_product_path(path) or any(hint in combined for hint in SHOPPING_PATH_HINTS)


def _path_tokens(path: str):
    return [
        token.lower()
        for token in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", unquote(path or ""))
        if len(token) > 1 and token.lower() not in GENERIC_PATH_WORDS
    ]


def _query_overlap_score(path: str, host: str, query: str | None) -> tuple[int, float]:
    query_tokens = _query_tokens(query)
    if not query_tokens:
        return 0, 0.0
    haystack = f"{host} {unquote(path)}".lower().replace("-", " ").replace("_", " ")
    matched = sum(1 for token in query_tokens if token in haystack)
    return matched, matched / max(1, len(query_tokens))


def _looks_like_short_category_path(path: str, host: str, query: str | None) -> bool:
    if not _is_broad_query(query) or _has_product_path(path):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not 1 <= len(segments) <= 2:
        return False
    _, overlap = _query_overlap_score(path, host, query)
    if overlap < 0.75:
        return False
    final_segment = segments[-1]
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", final_segment)
    has_model_reference = any(any(c.isalpha() for c in token) and any(c.isdigit() for c in token) for token in tokens)
    return not has_model_reference


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
    if _is_discovery_only_host(host):
        return True
    if _is_comparison_or_editorial_host(host):
        return True
    if host == "bing.com" and path.startswith("/aclick"):
        return True
    if any(marker in path for marker in BLOCKED_PATH_MARKERS):
        return True
    if host.endswith("fnac.com") and FNAC_LISTING_PATTERN.search(path):
        return True
    if host.endswith("ebay.com") and path.startswith("/shop"):
        return True
    if "amazon." in host and path.rstrip("/").endswith("/s") and "k" in query_params:
        return True
    if re.search(r"\.(pdf|txt|docx?|epub|xml|csv|zip)$", path):
        return True
    if "?s=" in url.lower() or "search=" in query_string or "query=" in query_string:
        return True

    if query and _is_broad_query(query):
        if _looks_editorial(host, path) and not _has_product_path(path):
            return True
        if _looks_like_short_category_path(path, host, query):
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

    if _has_product_path(path): score += 8
    if re.search(r"\b(\d+)(gb|go|tb|to|ssd|hdd)\b", path): score += 2
    path_tokens = _path_tokens(path)
    if len(path_tokens) >= 3: score += 2
    elif len(path_tokens) >= 1: score += 1
    if _looks_like_shopping_url(host, path): score += 2
    matched, ratio = _query_overlap_score(path, host, query)
    score += min(matched * 2, 6)
    if ratio >= 0.75: score += 4
    elif ratio >= 0.50: score += 2
    if any(any(char.isdigit() for char in token) and any(char.isalpha() for char in token) for token in path_tokens): score += 2
    if any(marker in path for marker in AMBIGUOUS_PATH_MARKERS) and not _has_product_path(path): score -= 3
    if _looks_editorial(host, path) and not _has_product_path(path): score -= 6
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) <= 1 and not _has_product_path(path): score -= 2
    if is_low_value_candidate_url(url, query=query): score -= 20
    return score


def filter_and_rank_candidate_urls(urls, health_score_func=None, query: str | None = None):
    unique = []
    seen = set()
    for url in urls or []:
        if not url or url in seen: continue
        seen.add(url)
        if not is_low_value_candidate_url(url, query=query): unique.append(url)
    if health_score_func is None:
        return sorted(unique, key=lambda value: product_url_score(value, query=query), reverse=True)
    return sorted(unique, key=lambda value: (product_url_score(value, query=query), health_score_func(value)), reverse=True)
