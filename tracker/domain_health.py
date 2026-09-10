from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings

from tracker.models import ScrapeJob


def domain_from_url(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.") or "unknown"


def domain_health(domain: str, sample_size: int | None = None) -> dict:
    """Score a domain from its most recent terminal scrape jobs.

    Unknown/new domains stay neutral so Bendango keeps exploring the market.
    """
    sample_size = sample_size or int(getattr(settings, "DOMAIN_HEALTH_SAMPLE_SIZE", 12))
    rows = list(
        ScrapeJob.objects.filter(
            url__icontains=domain,
            status__in=[ScrapeJob.STATUS_SUCCESS, ScrapeJob.STATUS_FAILED],
        )
        .order_by("-finished_at", "-created_at")
        .values("status", "fetch_status")[:max(1, sample_size)]
    )
    total = len(rows)
    successes = sum(1 for row in rows if row["status"] == ScrapeJob.STATUS_SUCCESS)
    fetch_failures = sum(1 for row in rows if row["fetch_status"] in {"fetch_failed", "anti_bot"})
    extraction_failures = sum(1 for row in rows if row["fetch_status"] == "extraction_failed")

    min_samples = int(getattr(settings, "DOMAIN_HEALTH_MIN_SAMPLES", 4))
    if total < min_samples:
        score = 0.5
    else:
        success_rate = successes / total
        penalty = (0.10 * (fetch_failures / total)) + (0.05 * (extraction_failures / total))
        score = max(0.0, min(1.0, success_rate - penalty))

    return {
        "domain": domain,
        "sample_size": total,
        "successes": successes,
        "score": round(score, 4),
    }


def url_domain_health_score(url: str) -> float:
    return domain_health(domain_from_url(url))["score"]


def rank_urls_by_domain_health(urls):
    """Prefer historically productive domains while preserving exploration."""
    indexed = list(enumerate(urls or []))
    scored = []
    cache = {}
    for index, url in indexed:
        domain = domain_from_url(url)
        if domain not in cache:
            cache[domain] = domain_health(domain)
        health = cache[domain]
        # Neutral/new domains rank ahead of known-bad domains, but good known domains
        # rank highest. Original order breaks ties to preserve search-engine relevance.
        scored.append((health["score"], index, url))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, _, url in scored]
