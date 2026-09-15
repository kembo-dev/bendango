from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone

from tracker.models import ScrapeJob


def domain_from_url(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.") or "unknown"


def domain_health(domain: str, sample_size: int | None = None) -> dict:
    """Score a domain from recent terminal scrape outcomes.

    The score starts neutral (0.50), reacts from the very first recent outcome,
    rewards proven fetch/extraction success, and progressively penalizes transport
    or non-product pages. The memory is time-bounded so domains rehabilitate
    automatically instead of being permanently blacklisted.
    """
    sample_size = sample_size or int(getattr(settings, "DOMAIN_HEALTH_SAMPLE_SIZE", 12))
    window_hours = max(1, int(getattr(settings, "DOMAIN_HEALTH_WINDOW_HOURS", 24)))
    cutoff = timezone.now() - timedelta(hours=window_hours)
    rows = list(
        ScrapeJob.objects.filter(
            url__icontains=domain,
            status__in=[ScrapeJob.STATUS_SUCCESS, ScrapeJob.STATUS_FAILED],
            finished_at__gte=cutoff,
        )
        .order_by("-finished_at", "-created_at")
        .values("status", "fetch_status")[:max(1, sample_size)]
    )

    total = len(rows)
    successes = sum(1 for row in rows if row["status"] == ScrapeJob.STATUS_SUCCESS)
    fetch_failures = sum(1 for row in rows if row["fetch_status"] in {"fetch_failed", "anti_bot"})
    no_product_structure = sum(1 for row in rows if row["fetch_status"] == "no_product_structure")
    extraction_failures = sum(1 for row in rows if row["fetch_status"] == "extraction_failed")
    product_mismatches = sum(1 for row in rows if row["fetch_status"] == "product_mismatch")

    if not rows:
        score = 0.50
    else:
        # New evidence matters immediately. Success is deliberately stronger than
        # one isolated failure so a productive new merchant can rise quickly.
        success_bonus = min(0.36, successes * 0.18)
        fetch_penalty = min(0.38, fetch_failures * 0.10)
        structure_penalty = min(0.24, no_product_structure * 0.08)
        extraction_penalty = min(0.16, extraction_failures * 0.05)
        mismatch_penalty = min(0.12, product_mismatches * 0.03)
        score = 0.50 + success_bonus - fetch_penalty - structure_penalty - extraction_penalty - mismatch_penalty
        score = max(0.0, min(1.0, score))

    return {
        "domain": domain,
        "sample_size": total,
        "successes": successes,
        "fetch_failures": fetch_failures,
        "no_product_structure": no_product_structure,
        "extraction_failures": extraction_failures,
        "product_mismatches": product_mismatches,
        "score": round(score, 4),
        "window_hours": window_hours,
    }


def domain_fetch_circuit_open(domain: str) -> bool:
    """Temporarily pause domains with consecutive recent transport failures."""
    if not domain or domain == "unknown":
        return False
    threshold = max(2, int(getattr(settings, "DOMAIN_FETCH_CIRCUIT_FAILURES", 2)))
    cooldown_minutes = max(1, int(getattr(settings, "DOMAIN_FETCH_CIRCUIT_MINUTES", 10)))
    cutoff = timezone.now() - timedelta(minutes=cooldown_minutes)
    rows = list(
        ScrapeJob.objects.filter(
            url__icontains=domain,
            status__in=[ScrapeJob.STATUS_SUCCESS, ScrapeJob.STATUS_FAILED],
            finished_at__gte=cutoff,
        )
        .order_by("-finished_at", "-created_at")
        .values("status", "fetch_status")[:threshold]
    )
    if len(rows) < threshold:
        return False
    return all(
        row["status"] == ScrapeJob.STATUS_FAILED and row["fetch_status"] in {"fetch_failed", "anti_bot"}
        for row in rows
    )


def url_domain_health_score(url: str) -> float:
    return domain_health(domain_from_url(url))["score"]


def domain_candidate_cap(domain: str, default_cap: int = 3) -> int:
    default_cap = max(1, int(default_cap))
    health = domain_health(domain)
    if health["sample_size"] == 0:
        return min(default_cap, 2)
    if health["score"] < 0.25:
        return 1
    if health["score"] < 0.50:
        return min(default_cap, 2)
    return default_cap


def domain_fetch_budget(domain: str) -> dict:
    """Return a bounded transport budget learned from recent domain outcomes."""
    health = domain_health(domain)
    normal_attempts = max(1, int(getattr(settings, "COLLECTION_MAX_ATTEMPTS", 3)))
    legacy = float(getattr(settings, "COLLECTION_TIMEOUT", 20))
    normal_connect = float(getattr(settings, "COLLECTION_CONNECT_TIMEOUT", min(4.0, legacy)))
    normal_read = float(getattr(settings, "COLLECTION_READ_TIMEOUT", min(8.0, legacy)))

    if health["sample_size"] == 0:
        tier = "explore"
        attempts = 1
        connect = min(normal_connect, float(getattr(settings, "COLLECTION_EXPLORE_CONNECT_TIMEOUT", 2.0)))
        read = min(normal_read, float(getattr(settings, "COLLECTION_EXPLORE_READ_TIMEOUT", 4.0)))
    elif health["score"] < 0.25:
        tier = "low"
        attempts = 1
        connect = min(normal_connect, float(getattr(settings, "COLLECTION_LOW_HEALTH_CONNECT_TIMEOUT", 2.0)))
        read = min(normal_read, float(getattr(settings, "COLLECTION_LOW_HEALTH_READ_TIMEOUT", 4.0)))
    elif health["score"] < 0.55:
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
