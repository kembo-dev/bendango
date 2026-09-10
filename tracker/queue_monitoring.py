from __future__ import annotations

from collections import Counter, defaultdict
from urllib.parse import urlparse

from django.db.models import Avg, Count

from tracker.models import ScrapeJob


def _domain(url: str) -> str:
    return urlparse(url or "").netloc.lower().removeprefix("www.") or "unknown"


def queue_metrics(limit_domains: int = 10) -> dict:
    """Return operational metrics for the persistent scrape queue."""
    status_counts = {key: 0 for key, _ in ScrapeJob.STATUS_CHOICES}
    for row in ScrapeJob.objects.values("status").annotate(total=Count("id")):
        status_counts[row["status"]] = row["total"]

    terminal = status_counts[ScrapeJob.STATUS_SUCCESS] + status_counts[ScrapeJob.STATUS_FAILED]
    success_rate = (status_counts[ScrapeJob.STATUS_SUCCESS] / terminal) if terminal else 0.0
    backlog = (
        status_counts[ScrapeJob.STATUS_PENDING]
        + status_counts[ScrapeJob.STATUS_RETRY]
        + status_counts[ScrapeJob.STATUS_RUNNING]
    )

    avg_duration = ScrapeJob.objects.exclude(duration_ms=0).aggregate(value=Avg("duration_ms"))["value"] or 0
    cache_hits = ScrapeJob.objects.filter(from_cache=True).count()
    anti_bot = ScrapeJob.objects.filter(fetch_status="anti_bot").count()
    total = ScrapeJob.objects.count()

    domains = defaultdict(lambda: {"total": 0, "success": 0, "failed": 0, "retry": 0, "anti_bot": 0, "duration_sum": 0, "duration_n": 0})
    for job in ScrapeJob.objects.all().only("url", "status", "fetch_status", "duration_ms"):
        item = domains[_domain(job.url)]
        item["total"] += 1
        if job.status == ScrapeJob.STATUS_SUCCESS:
            item["success"] += 1
        elif job.status == ScrapeJob.STATUS_FAILED:
            item["failed"] += 1
        elif job.status == ScrapeJob.STATUS_RETRY:
            item["retry"] += 1
        if job.fetch_status == "anti_bot":
            item["anti_bot"] += 1
        if job.duration_ms:
            item["duration_sum"] += job.duration_ms
            item["duration_n"] += 1

    domain_rows = []
    for domain, values in domains.items():
        terminal_domain = values["success"] + values["failed"]
        domain_rows.append({
            "domain": domain,
            "total": values["total"],
            "success": values["success"],
            "failed": values["failed"],
            "retry": values["retry"],
            "anti_bot": values["anti_bot"],
            "success_rate": (values["success"] / terminal_domain) if terminal_domain else 0.0,
            "avg_duration_ms": round(values["duration_sum"] / values["duration_n"]) if values["duration_n"] else 0,
        })

    domain_rows.sort(key=lambda row: (row["failed"] + row["retry"] + row["anti_bot"], row["total"]), reverse=True)

    failure_reasons = Counter(
        ScrapeJob.objects.filter(status=ScrapeJob.STATUS_FAILED)
        .exclude(fetch_status="")
        .values_list("fetch_status", flat=True)
    )

    return {
        "total": total,
        "backlog": backlog,
        "status": status_counts,
        "success_rate": round(success_rate, 4),
        "avg_duration_ms": round(float(avg_duration), 1),
        "cache_hits": cache_hits,
        "cache_hit_rate": round(cache_hits / total, 4) if total else 0.0,
        "anti_bot": anti_bot,
        "anti_bot_rate": round(anti_bot / total, 4) if total else 0.0,
        "failure_reasons": dict(failure_reasons.most_common()),
        "domains": domain_rows[:max(1, limit_domains)],
    }
