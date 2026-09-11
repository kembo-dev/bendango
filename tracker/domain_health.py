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
        penalty = (0.20 * (fetch_failures / total)) + (0.08 * (extraction_failures / total))
        score = max(0.0, min(1.0, success_rate - penalty))

    return {
        "domain": domain,
        "sample_size": total,
        "successes": successes,
        "fetch_failures": fetch_failures,
        "extraction_failures": extraction_failures,
        "score": round(score, 4),
    }


def url_domain_health_score(url: str) -> float:
    return domain_health(domain_from_url(url))["score"]


def domain_candidate_cap(domain: str, default_cap: int = 3) -> int:
    default_cap = max(1, int(default_cap))
    health = domain_health(domain)
    min_samples = int(getattr(settings, "DOMAIN_HEALTH_MIN_SAMPLES", 4))
    if health["sample_size"] < min_samples:
        return min(default_cap, 2)
    if health["score"] < 0.20:
        return 1
    if health["score"] < 0.50:
        return min(default_cap, 2)
    return default_cap


def domain_fetch_budget(domain: str) -> dict:
    """Return a bounded transport budget learned from recent domain outcomes.

    New domains remain explorable, but each exploration pass is intentionally
    cheap. A failed exploratory job can still receive the queue-level delayed
    retry, so the domain gets a second chance without multiplying inner retries.
    """
    health = domain_health(domain)
    min_samples = int(getattr(settings, "DOMAIN_HEALTH_MIN_SAMPLES", 4))
    normal_attempts = max(1, int(getattr(settings, "COLLECTION_MAX_ATTEMPTS", 3)))
    legacy = float(getattr(settings, "COLLECTION_TIMEOUT", 20))
    normal_connect = float(getattr(settings, "COLLECTION_CONNECT_TIMEOUT", min(4.0, legacy)))
    normal_read = float(getattr(settings, "COLLECTION_READ_TIMEOUT", min(8.0, legacy)))

    if health["sample_size"] < min_samples:
        tier = "explore"
        attempts = 1
        connect = min(normal_connect, float(getattr(settings, "COLLECTION_EXPLORE_CONNECT_TIMEOUT", 2.0)))
        read = min(normal_read, float(getattr(settings, "COLLECTION_EXPLORE_READ_TIMEOUT", 4.0)))
    elif health["score"] < 0.20:
        tier = "low"
        attempts = 1
        connect = min(normal_connect, float(getattr(settings, "COLLECTION_LOW_HEALTH_CONNECT_TIMEOUT", 2.0)))
        read = min(normal_read, float(getattr(settings, "COLLECTION_LOW_HEALTH_READ_TIMEOUT", 4.0)))
    elif health["score"] < 0.50:
        tier = "limited"
        attempts = min(normal_attempts, 2)
        connect = min(normal_connect, float(getattr(settings, "COLLECTION_LIMITED_HEALTH_CONNECT_TIMEOUT", 3.0)))
        read = min(normal_read, float(getattr(settings, "COLLECTION_LIMITED_HEALTH_READ_TIMEOUT", 6.0)))
    else:
        tier = "healthy"
        attempts = normal_attempts
        connect, read = normal_connect, normal_read

    return {
        "domain": domain,
        "tier": tier,
        "score": health["score"],
        "sample_size": health["sample_size"],
        "max_attempts": attempts,
        "timeout": (max(0.5, connect), max(1.0, read)),
    }


def url_fetch_budget(url: str) -> dict:
    return domain_fetch_budget(domain_from_url(url))


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
        scored.append((health["score"], index, url))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, _, url in scored]
