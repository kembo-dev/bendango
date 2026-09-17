from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from urllib.parse import urlparse

from ddgs import DDGS

from tracker.markets import DEFAULT_MARKET_CODE, get_market, market_search_label
from tracker.product_matching import match_product, normalize_product_name


DISCOVERY_HOSTS = {
    "facebook.com": "Facebook", "fb.com": "Facebook", "instagram.com": "Instagram", "tiktok.com": "TikTok",
    "youtube.com": "YouTube", "youtu.be": "YouTube", "reddit.com": "Reddit", "pinterest.com": "Pinterest",
    "x.com": "X", "twitter.com": "X", "linkedin.com": "LinkedIn", "lesnumeriques.com": "Les Numériques",
    "kimovil.com": "Kimovil", "idealo.fr": "Idealo", "123comparer.fr": "123comparer", "accio.com": "Accio",
    "chooseyourmobile.com": "ChooseYourMobile", "kalvo.com": "Kalvo", "mobolist.net": "Mobolist",
}
SOCIAL_PLATFORMS = {"Facebook", "Instagram", "TikTok", "YouTube", "Reddit", "Pinterest", "X", "LinkedIn"}
COMPARISON_PLATFORMS = {"Kimovil", "Idealo", "123comparer", "Accio"}
INFORMATIVE_PLATFORMS = {"Les Numériques", "ChooseYourMobile", "Kalvo", "Mobolist"}
SOCIAL_COMMERCE_TERMS = {
    "prix", "price", "vente", "vendre", "vend", "acheter", "buy", "shop", "store", "boutique", "disponible",
    "available", "stock", "livraison", "delivery", "commande", "commander", "order", "promo", "promotion",
    "cdf", "usd", "eur", "cad", "xof", "xaf", "mad", "ngn", "kes", "tzs", "$", "€",
}
ACCESSORY_TERMS = {
    "chaise", "chair", "manette", "controller", "coque", "case", "cover", "cable", "câble", "chargeur",
    "charger", "support", "stand", "sac", "bag", "étui", "etui", "accessoire", "accessory",
}
IGNORED_HOSTS = {"archive.org", "web.archive.org", "wikipedia.org"}
IGNORED_EXTENSIONS = (".txt", ".pdf", ".epub", ".doc", ".docx", ".xml", ".csv", ".zip")
GENERIC_QUERY_WORDS = {"prix", "price", "acheter", "buy", "vente", "disponible", "available"}


@dataclass(frozen=True)
class DiscoverySource:
    url: str
    platform: str
    title: str
    snippet: str = ""
    relevance_score: float = 0.0
    source_type: str = ""


def source_type_for_platform(platform: str) -> str:
    if platform in SOCIAL_PLATFORMS:
        return "Réseau social"
    if platform in COMPARISON_PLATFORMS:
        return "Comparateur"
    if platform in INFORMATIVE_PLATFORMS:
        return "Fiche informative"
    return "Autre source"


def discovery_sources_to_json(sources) -> list[dict]:
    serialized = []
    for source in sources or []:
        if isinstance(source, dict):
            item = dict(source)
        elif is_dataclass(source):
            item = asdict(source)
        else:
            item = {
                "url": str(getattr(source, "url", "") or ""), "platform": str(getattr(source, "platform", "") or ""),
                "title": str(getattr(source, "title", "") or ""), "snippet": str(getattr(source, "snippet", "") or ""),
                "relevance_score": float(getattr(source, "relevance_score", 0.0) or 0.0),
                "source_type": str(getattr(source, "source_type", "") or ""),
            }
        if not item.get("source_type"):
            item["source_type"] = source_type_for_platform(str(item.get("platform") or ""))
        serialized.append(item)
    return serialized


def _normalized_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _host_matches(host: str, candidate: str) -> bool:
    return host == candidate or host.endswith("." + candidate)


def classify_url(url: str) -> str:
    parsed = urlparse(url); host = parsed.netloc.lower().removeprefix("www."); path = parsed.path.lower()
    if any(_host_matches(host, blocked) for blocked in IGNORED_HOSTS) or path.endswith(IGNORED_EXTENSIONS):
        return "ignored"
    if any(_host_matches(host, candidate) for candidate in DISCOVERY_HOSTS):
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
    return {token for token in normalized.split() if len(token) >= 2 and token not in GENERIC_QUERY_WORDS}


def _token_coverage(query: str, text: str) -> float:
    query_tokens = _meaningful_query_tokens(query)
    if not query_tokens:
        return 0.0
    text_tokens = set(normalize_product_name(text).split())
    return len(query_tokens & text_tokens) / len(query_tokens)


def _reference_tokens(query: str) -> set[str]:
    return {token for token in re.findall(r"\b[a-z0-9-]+\b", normalize_product_name(query)) if any(c.isalpha() for c in token) and any(c.isdigit() for c in token)}


def _has_required_reference_tokens(query: str, text: str) -> bool:
    references = _reference_tokens(query)
    if not references:
        return True
    text_tokens = set(re.findall(r"\b[a-z0-9-]+\b", normalize_product_name(text)))
    return references.issubset(text_tokens)


def _has_important_numeric_token(query: str, text: str) -> bool:
    numbers = set(re.findall(r"\b\d+[a-z]*\b", normalize_product_name(query)))
    if not numbers:
        return True
    return numbers.issubset(set(re.findall(r"\b\d+[a-z]*\b", normalize_product_name(text))))


def _has_social_commerce_signal(text: str) -> bool:
    normalized = normalize_product_name(text)
    tokens = set(normalized.split())
    return any(term in tokens for term in SOCIAL_COMMERCE_TERMS if term.isalnum()) or "$" in text or "€" in text


def _market_terms(market_code: str) -> set[str]:
    market = get_market(market_code)
    return {normalize_product_name(term) for term in (*market.hints, *market.cities, market.country) if term}


def _has_local_signal(text: str, market_code: str = DEFAULT_MARKET_CODE) -> bool:
    normalized = normalize_product_name(text)
    return any(term and (term in normalized.split() or term in normalized) for term in _market_terms(market_code))


def _looks_like_accessory_for_broad_query(query: str, text: str) -> bool:
    query_tokens = _meaningful_query_tokens(query)
    if len(query_tokens) > 1:
        return False
    normalized_query = normalize_product_name(query); normalized_text = normalize_product_name(text)
    if any(term in normalized_query.split() for term in ACCESSORY_TERMS):
        return False
    return any(term in normalized_text.split() for term in ACCESSORY_TERMS)


def _is_relevant_discovery_result(query: str, platform: str, title: str, snippet: str, market_code: str = DEFAULT_MARKET_CODE) -> tuple[bool, float]:
    combined = f"{title} {snippet}".strip()
    if not combined:
        return False, 0.0
    coverage = _token_coverage(query, combined); match = match_product(query, combined, threshold=0.72)
    broad_query = len(_meaningful_query_tokens(query)) <= 1
    if platform == "Facebook":
        if coverage < 0.75 or not _has_important_numeric_token(query, combined) or not _has_required_reference_tokens(query, combined):
            return False, match.score
        if broad_query and (not _has_social_commerce_signal(combined) or not _has_local_signal(combined, market_code)):
            return False, match.score
        if _looks_like_accessory_for_broad_query(query, combined) or not match.is_match or match.score < 0.82:
            return False, match.score
        return True, match.score
    if platform in SOCIAL_PLATFORMS:
        if coverage < 0.55 or not _has_required_reference_tokens(query, combined):
            return False, match.score
        if broad_query and (not _has_social_commerce_signal(combined) or not _has_local_signal(combined, market_code)):
            return False, match.score
        if _looks_like_accessory_for_broad_query(query, combined) or (not match.is_match and match.score < 0.68):
            return False, match.score
        return True, max(match.score, coverage)
    if coverage < 0.50 or not _has_required_reference_tokens(query, combined) or (not match.is_match and match.score < 0.62):
        return False, match.score
    return True, max(match.score, coverage)


def discover_discovery_sources(query: str, max_results: int = 8, market_code: str = DEFAULT_MARKET_CODE) -> list[DiscoverySource]:
    if not query:
        return []
    local_label = market_search_label(market_code)
    search_terms = [
        f'"{query}" {local_label} Facebook Instagram TikTok',
        f'"{query}" {get_market(market_code).country} prix price avis comparatif fiche technique',
    ]
    found: list[DiscoverySource] = []; seen: set[str] = set()
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
                platform = platform_for_url(url); title = str(result.get("title") or platform).strip()
                snippet = str(result.get("body") or result.get("snippet") or "").strip()
                relevant, score = _is_relevant_discovery_result(query, platform, title, snippet, market_code=market_code)
                if not relevant:
                    continue
                seen.add(url)
                found.append(DiscoverySource(url=url, platform=platform, title=title, snippet=snippet[:240], relevance_score=score, source_type=source_type_for_platform(platform)))
    found.sort(key=lambda item: item.relevance_score, reverse=True)
    return found[:max_results]


def discover_social_sources(query: str, max_results: int = 8, market_code: str = DEFAULT_MARKET_CODE) -> list[DiscoverySource]:
    return discover_discovery_sources(query, max_results=max_results, market_code=market_code)
