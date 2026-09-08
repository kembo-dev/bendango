from __future__ import annotations

from urllib.parse import quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from tracker.product_matching import match_product


def _headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    }


def _search_urls_for_domain(domain: str, query: str) -> list[str]:
    """Try common storefront search patterns without vendor-specific rules."""
    encoded = quote_plus(query)
    base = f"https://{domain}"
    return [
        f"{base}/search?q={encoded}",
        f"{base}/?s={encoded}&post_type=product",
        f"{base}/?s={encoded}",
    ]


def _looks_like_product_path(path: str) -> bool:
    path = path.lower()
    return any(token in path for token in (
        "/product/", "/products/", "/produit/", "/produits/",
        "/item/", "/items/", "/p/",
    ))


def discover_product_urls(query: str, domains: list[str], max_results: int = 3) -> list[str]:
    """Search already-known merchant domains as a secondary fallback only."""
    if not query:
        return []

    session = requests.Session()
    session.headers.update(_headers())
    found: list[tuple[float, str]] = []

    for raw_domain in domains:
        domain = (raw_domain or "").strip().lower().removeprefix("www.")
        if not domain:
            continue

        for search_url in _search_urls_for_domain(domain, query):
            try:
                response = session.get(search_url, timeout=12, allow_redirects=True)
                response.raise_for_status()
            except requests.RequestException:
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = urljoin(response.url, link.get("href"))
                parsed = urlparse(href)
                host = parsed.netloc.lower().removeprefix("www.")
                if host != domain and not host.endswith("." + domain):
                    continue
                if not _looks_like_product_path(parsed.path):
                    continue

                image = link.find("img")
                title = " ".join([
                    link.get("title", ""),
                    link.get_text(" ", strip=True),
                    (image.get("alt", "") if image else ""),
                ]).strip()
                if not title:
                    continue

                result = match_product(query, title, threshold=0.62)
                if not result.is_match:
                    continue

                clean_url = href.split("#", 1)[0]
                if any(existing_url == clean_url for _, existing_url in found):
                    continue
                found.append((result.score, clean_url))

    found.sort(key=lambda item: item[0], reverse=True)
    return [url for _, url in found[:max_results]]
