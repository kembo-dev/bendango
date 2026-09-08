from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from ddgs import DDGS

from tracker.product_matching import match_product, normalize_product_name


DISCOVERY_HOSTS = {
    "facebook.com": "Facebook",
    "fb.com": "Facebook",
    "instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "reddit.com": "Reddit",
    "pinterest.com": "Pinterest",
    "x.com": "X",
    "twitter.com": "X",
    "linkedin.com": "LinkedIn",
}

IGNORED_HOSTS = {
    "archive.org",
    "web.archive.org",
    "wikipedia.org",
}

IGNORED_EXTENSIONS = (".txt", ".pdf", ".epub", ".doc", ".docx", ".xml", ".csv", ".zip")
GENERIC_QUERY_WORDS = {"rdc", "kinshasa", "prix", "acheter", "vente", "disponible", "congo"}


@dataclass(frozen=True)
class DiscoverySource:
    url: str
    platform: str
    title: str
    snippet: str = ""
    relevance_score: float = 0.0


def _normalized_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _host_matches(host: str, candidate: str) -> bool:
    return host == candidate or host.endswith("." + candidate)


def classify_url(url: str) -> str:
    """Return verified_offer, discovery_source or ignored."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()

    if any(_host_matches(host, blocked) for blocked in IGNORED_HOSTS):
        return "ignored"
    if path.endswith(IGNORED_EXTENSIONS):
        return "ignored"
    if any(_host_matches(host, social) for social in DISCOVERY_HOSTS):
        return "discovery_source"
    return "verified_offer"


def platform_for_url(url: str) -> str:
    host = _normalized_host(url)
    for candidate, label in DISCOVERY_HOSTS.items():
        if _host_matches(host, candidate):
            return label
    return "Autre source"


def _meaningful_query_tokens(query: str) -> set[str]:
    normalized = normalize_product_name(query)
    return {
        token for token in normalized.split()
        if len(token) >= 2 and token not in GENERIC_QUERY_WORDS
    }


def _token_coverage(query: str, text: str) -> float:
    query_tokens = _meaningful_query_tokens(query)
    if not query_tokens:
        return 0.0
    text_tokens = set(normalize_product_name(text).split())
    return len(query_tokens & text_tokens) / len(query_tokens)


def _has_important_numeric_token(query: str, text: str) -> bool:
    numbers = set(re.findall(r"\b\d+[a-z]*\b", normalize_product_name(query)))
    if not numbers:
        return True
    text_numbers = set(re.findall(r"\b\d+[a-z]*\b", normalize_product_name(text)))
    return numbers.issubset(text_numbers)


def _is_relevant_discovery_result(query: str, platform: str, title: str, snippet: str) -> tuple[bool, float]:
    combined = f"{title} {snippet}".strip()
    if not combined:
        return False, 0.0

    coverage = _token_coverage(query, combined)
    match = match_product(query, combined, threshold=0.72)

    if platform == "Facebook":
        # Facebook search snippets are particularly noisy. Require strong token
        # coverage, compatible numeric/model tokens and a high matcher score.
        if coverage < 0.75:
            return False, match.score
        if not _has_important_numeric_token(query, combined):
            return False, match.score
        if not match.is_match or match.score < 0.82:
            return False, match.score
        return True, match.score

    # Other discovery platforms remain useful but still need reasonable evidence.
    if coverage < 0.55:
        return False, match.score
    if not match.is_match and match.score < 0.68:
        return False, match.score
    return True, max(match.score, coverage)


def discover_social_sources(query: str, max_results: int = 8) -> list[DiscoverySource]:
    """Find social/discovery results without treating them as verified offers."""
    if not query:
        return []

    search_terms = [
        f'"{query}" RDC Kinshasa Facebook Instagram TikTok',
        f'"{query}" Kinshasa YouTube Reddit',
    ]
    found: list[DiscoverySource] = []
    seen: set[str] = set()

    with DDGS() as ddgs:
        for term in search_terms:
            try:
                results = ddgs.text(term, max_results=max_results * 2)
            except Exception:
                continue
            for result in results:
                url = str(result.get("href") or "").strip()
                if not url or url in seen or classify_url(url) != "discovery_source":
                    continue

                platform = platform_for_url(url)
                title = str(result.get("title") or platform).strip()
                snippet = str(result.get("body") or result.get("snippet") or "").strip()
                relevant, score = _is_relevant_discovery_result(query, platform, title, snippet)
                if not relevant:
                    continue

                seen.add(url)
                found.append(
                    DiscoverySource(
                        url=url,
                        platform=platform,
                        title=title,
                        snippet=snippet[:240],
                        relevance_score=score,
                    )
                )

    found.sort(key=lambda item: item.relevance_score, reverse=True)
    return found[:max_results]
