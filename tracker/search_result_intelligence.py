from __future__ import annotations

import re
from dataclasses import dataclass

from ddgs import DDGS
from django.conf import settings

from tracker.candidate_filter import is_low_value_candidate_url, product_url_score


COMMERCE_TERMS = (
    'prix', 'price', 'acheter', 'buy', 'commander', 'order', 'livraison', 'delivery',
    'en stock', 'in stock', 'disponible', 'available', 'panier', 'cart', 'boutique',
    'shop', 'store', 'vente', 'sold by', 'usd', 'eur', 'cdf', 'cfa', 'fcfa', '$', '€',
)

EDITORIAL_TERMS = (
    'guide', 'comment choisir', 'how to choose', 'conseil', 'conseils', 'astuce', 'astuces',
    'comparatif', 'comparison', 'review', 'avis', 'test complet', 'actualité', 'actualite',
    'news', 'blog', 'tutoriel', 'tutorial', 'définition', 'definition', 'wikipedia',
)

GENERIC_RESULT_TERMS = (
    'accueil', 'home page', 'catalogue', 'catalog', 'nos produits', 'our products',
    'mode femme', 'mode homme', 'boutique en ligne', 'online store',
)

DEFAULT_DDGS_BACKENDS = ('auto', 'google,brave,duckduckgo', 'bing,yahoo')


@dataclass(frozen=True)
class SearchCandidate:
    url: str
    title: str = ''
    snippet: str = ''
    search_score: float = 0.0


def _tokens(value: str | None) -> list[str]:
    return [token.lower() for token in re.findall(r'[a-zA-ZÀ-ÿ0-9]+', value or '') if len(token) > 1]


def _query_overlap(query: str | None, text: str) -> tuple[int, float]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0, 0.0
    haystack = (text or '').lower()
    matched = sum(1 for token in query_tokens if token in haystack)
    return matched, matched / max(1, len(query_tokens))


def _ddgs_backend_attempts() -> tuple[str, ...]:
    configured = getattr(settings, 'DDGS_BACKENDS', None)
    if isinstance(configured, str) and configured.strip():
        attempts = tuple(part.strip() for part in configured.split('|') if part.strip())
        if attempts:
            return attempts
    if isinstance(configured, (list, tuple)):
        attempts = tuple(str(part).strip() for part in configured if str(part).strip())
        if attempts:
            return attempts
    return DEFAULT_DDGS_BACKENDS


def _search_ddgs_with_fallback(search_term: str, max_results: int):
    timeout = max(2, int(getattr(settings, 'DDGS_TIMEOUT', 8)))
    last_error = None
    for backend in _ddgs_backend_attempts():
        try:
            with DDGS(timeout=timeout) as ddgs:
                results = ddgs.text(search_term, max_results=max_results, backend=backend)
            if results:
                return results
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return []


def search_metadata_score(title: str, snippet: str, query: str | None = None) -> float:
    """Score DDGS title/snippet before Bendango spends a product-page fetch."""
    title = (title or '').strip()
    snippet = (snippet or '').strip()
    title_lower = title.lower()
    combined = f'{title} {snippet}'.lower()
    score = 0.0

    title_matches, title_ratio = _query_overlap(query, title)
    text_matches, text_ratio = _query_overlap(query, combined)

    score += min(title_matches * 3.0, 9.0)
    score += min(text_matches * 1.5, 6.0)
    if title_ratio >= 0.75:
        score += 7.0
    elif title_ratio >= 0.50:
        score += 4.0
    elif text_ratio >= 0.50:
        score += 2.0

    commerce_hits = sum(1 for term in COMMERCE_TERMS if term in combined)
    score += min(commerce_hits * 2.0, 8.0)

    # Prices visible directly in a snippet are a strong merchant-page signal.
    if re.search(r'(?:€|\$|usd|eur|cdf|cfa|fcfa)\s*\d|\d[\d\s.,]*\s*(?:€|\$|usd|eur|cdf|cfa|fcfa)', combined, re.I):
        score += 5.0

    editorial_hits = sum(1 for term in EDITORIAL_TERMS if term in combined)
    score -= min(editorial_hits * 4.0, 12.0)

    if any(term in title_lower for term in GENERIC_RESULT_TERMS) and title_ratio < 0.50:
        score -= 5.0

    # A title with no query overlap is suspicious for broad queries, but remains
    # rankable instead of being hard-blocked because merchant titles can be terse.
    if query and title and title_matches == 0:
        score -= 4.0

    return round(score, 2)


def clearly_low_value_search_result(title: str, snippet: str, query: str | None = None) -> bool:
    """Reject obvious editorial/noise results while keeping ambiguous merchants."""
    combined = f'{title or ""} {snippet or ""}'.lower()
    _, overlap = _query_overlap(query, combined)
    editorial_hits = sum(1 for term in EDITORIAL_TERMS if term in combined)
    commerce_hits = sum(1 for term in COMMERCE_TERMS if term in combined)
    return bool(editorial_hits >= 2 and commerce_hits == 0 and overlap < 0.50)


def collect_search_candidates(search_term: str, max_results: int, product_query: str | None = None):
    """Collect DDGS results with title/snippet intelligence.

    Results remain dictionaries so adaptive_engine can gracefully consume mocked
    legacy URL strings and enriched production candidates through the same path.
    DDGS is retried across independent backend groups so a single HTTP/2/TLS
    backend failure does not abort merchant discovery.
    """
    candidates = []
    seen = set()
    for result in _search_ddgs_with_fallback(search_term, max_results=max_results):
        url = str(result.get('href') or '').strip()
        if not url or url in seen or is_low_value_candidate_url(url, query=product_query):
            continue
        title = str(result.get('title') or '').strip()
        snippet = str(result.get('body') or result.get('snippet') or '').strip()
        if clearly_low_value_search_result(title, snippet, query=product_query):
            continue
        seen.add(url)
        metadata_score = search_metadata_score(title, snippet, query=product_query)
        candidates.append({
            'url': url,
            'title': title,
            'snippet': snippet,
            'search_score': metadata_score,
        })
    return candidates


def rank_search_candidates(candidates, query: str | None = None, health_score_func=None):
    """Rank enriched candidates; legacy URL strings remain fully supported."""
    normalized = []
    seen = set()
    for candidate in candidates or []:
        if isinstance(candidate, str):
            url = candidate
            metadata_score = 0.0
            payload = {'url': url, 'title': '', 'snippet': '', 'search_score': 0.0}
        else:
            url = str(candidate.get('url') or candidate.get('href') or '').strip()
            metadata_score = float(candidate.get('search_score') or 0.0)
            payload = {
                'url': url,
                'title': str(candidate.get('title') or ''),
                'snippet': str(candidate.get('snippet') or candidate.get('body') or ''),
                'search_score': metadata_score,
            }
        if not url or url in seen or is_low_value_candidate_url(url, query=query):
            continue
        seen.add(url)
        health = float(health_score_func(url)) if health_score_func else 0.5
        total = (product_url_score(url, query=query) * 10.0) + (metadata_score * 3.0) + (health * 8.0)
        normalized.append((total, payload))

    normalized.sort(key=lambda item: item[0], reverse=True)
    return [payload for _, payload in normalized]
