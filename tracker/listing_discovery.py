from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from tracker.candidate_filter import BLOCKED_HOSTS, FNAC_LISTING_PATTERN, is_low_value_candidate_url, product_url_score
from tracker.product_matching import match_product


DISCOVERY_PATH_MARKERS = (
    "/category", "/categories", "/categorie", "/cat/", "/collection", "/collections",
    "/search", "/browse/", "/brand/", "/brands/", "/shop/",
)

NON_DISCOVERY_PATH_MARKERS = (
    "/privacy", "/privacy-policy", "/policies/", "/terms", "/conditions",
    "/forum", "/forums", "/thread", "/threads", "/viewtopic", "/blog/",
    "/comparatif", "/compare", "/wiki", "/dictionary/",
)


def _host_matches(host: str, blocked: str) -> bool:
    return host == blocked or host.endswith("." + blocked)


def is_discovery_page_url(url: str) -> bool:
    """Return True for merchant listing/search pages useful only to discover detail URLs."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = (parsed.path or "").lower()
    query_params = parse_qs(parsed.query or "")

    if not host or any(_host_matches(host, blocked) for blocked in BLOCKED_HOSTS):
        return False
    if any(marker in path for marker in NON_DISCOVERY_PATH_MARKERS):
        return False
    if host.endswith("fnac.com") and FNAC_LISTING_PATTERN.search(path):
        return True
    if "amazon." in host and path.rstrip("/").endswith("/s") and "k" in query_params:
        return True
    if any(marker in path for marker in DISCOVERY_PATH_MARKERS):
        return True
    if "s" in query_params or "search" in query_params or "query" in query_params or "q" in query_params:
        return True
    return False


def _headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }


def discover_product_urls_from_pages(query: str, pages, max_pages: int = 6, max_results: int = 12):
    """Mine merchant listing pages for same-domain product detail links.

    Listing pages are never returned as offers themselves; they are navigation sources only.
    """
    if not query:
        return []

    session = requests.Session()
    session.headers.update(_headers())
    found = []
    seen = set()

    for page_url in [url for url in (pages or []) if is_discovery_page_url(url)][:max_pages]:
        parsed_page = urlparse(page_url)
        page_host = parsed_page.netloc.lower().removeprefix("www.")
        try:
            response = session.get(page_url, timeout=12, allow_redirects=True)
            response.raise_for_status()
        except requests.RequestException:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.find_all("a", href=True):
            href = urljoin(response.url, link.get("href"))
            parsed = urlparse(href)
            host = parsed.netloc.lower().removeprefix("www.")
            if host != page_host and not host.endswith("." + page_host):
                continue
            clean_url = href.split("#", 1)[0]
            if clean_url in seen or is_low_value_candidate_url(clean_url):
                continue

            image = link.find("img")
            title = " ".join(filter(None, [
                link.get("title", ""),
                link.get_text(" ", strip=True),
                image.get("alt", "") if image else "",
            ])).strip()
            path_score = product_url_score(clean_url)
            match = match_product(query, title, threshold=0.58) if title else None
            if path_score < 5 and not (match and match.is_match):
                continue
            if match and not match.is_match and path_score < 7:
                continue

            score = (match.score if match and match.is_match else 0.45) + (0.04 * max(path_score, 0))
            seen.add(clean_url)
            found.append((score, clean_url))

    found.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in found[:max_results]]
