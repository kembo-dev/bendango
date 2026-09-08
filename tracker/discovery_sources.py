from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from ddgs import DDGS


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


@dataclass(frozen=True)
class DiscoverySource:
    url: str
    platform: str
    title: str
    snippet: str = ""


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


def discover_social_sources(query: str, max_results: int = 8) -> list[DiscoverySource]:
    """Find social/discovery results without treating them as verified offers."""
    if not query:
        return []

    search_terms = [
        f'{query} RDC Kinshasa Facebook Instagram TikTok',
        f'{query} Kinshasa YouTube Reddit',
    ]
    found: list[DiscoverySource] = []
    seen: set[str] = set()

    with DDGS() as ddgs:
        for term in search_terms:
            try:
                results = ddgs.text(term, max_results=max_results)
            except Exception:
                continue
            for result in results:
                url = str(result.get("href") or "").strip()
                if not url or url in seen or classify_url(url) != "discovery_source":
                    continue
                seen.add(url)
                title = str(result.get("title") or platform_for_url(url)).strip()
                snippet = str(result.get("body") or result.get("snippet") or "").strip()
                found.append(
                    DiscoverySource(
                        url=url,
                        platform=platform_for_url(url),
                        title=title,
                        snippet=snippet[:240],
                    )
                )
                if len(found) >= max_results:
                    return found
    return found
