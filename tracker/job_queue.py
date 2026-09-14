from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.candidate_filter import product_url_score
from tracker.domain_health import domain_from_url, url_domain_health_score
from tracker.models import ScrapeJob


ACTIVE_STATUSES = (ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY, ScrapeJob.STATUS_RUNNING)
CLAIMABLE_STATUSES = (ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY)


def enqueue_scrape_job(url: str, query: str = '', model_name: str = '', max_attempts: int = 3) -> ScrapeJob:
    existing = ScrapeJob.objects.filter(url=url, query=query, status__in=ACTIVE_STATUSES).order_by('-created_at').first()
    if existing:
        return existing
    return ScrapeJob.objects.create(
        url=url,
        query=query or '',
        model_name=model_name or '',
        max_attempts=max(1, max_attempts),
        available_at=timezone.now(),
    )


def recover_stale_running_jobs(timeout_seconds: int | None = None) -> int:
    if timeout_seconds is None:
        timeout_seconds = int(getattr(settings, 'SCRAPE_JOB_RUNNING_TIMEOUT', 300))
    timeout_seconds = max(1, int(timeout_seconds))
    cutoff = timezone.now() - timedelta(seconds=timeout_seconds)
    stale_ids = list(
        ScrapeJob.objects.filter(
            status=ScrapeJob.STATUS_RUNNING,
            started_at__isnull=False,
            started_at__lt=cutoff,
        ).values_list('id', flat=True)
    )
    recovered = 0
    for job_id in stale_ids:
        with transaction.atomic():
            job = ScrapeJob.objects.filter(pk=job_id, status=ScrapeJob.STATUS_RUNNING).first()
            if not job:
                continue
            now = timezone.now()
            if job.attempts < job.max_attempts:
                job.status = ScrapeJob.STATUS_RETRY
                job.available_at = now
                job.last_error = 'Job running expiré: worker interrompu ou bloqué.'
            else:
                job.status = ScrapeJob.STATUS_FAILED
                job.last_error = 'Job running expiré après le nombre maximal de tentatives.'
            job.fetch_status = 'stale_worker'
            job.finished_at = now
            job.save(update_fields=['status', 'available_at', 'last_error', 'fetch_status', 'finished_at', 'updated_at'])
            recovered += 1
    return recovered


def claim_job(job_id: int) -> ScrapeJob | None:
    now = timezone.now()
    candidate = (
        ScrapeJob.objects.filter(
            pk=job_id,
            status__in=CLAIMABLE_STATUSES,
            available_at__lte=now,
        )
        .values('id', 'status', 'attempts')
        .first()
    )
    if not candidate:
        return None

    claimed_from_status = candidate['status']
    updated = ScrapeJob.objects.filter(
        pk=candidate['id'],
        status=candidate['status'],
        attempts=candidate['attempts'],
        available_at__lte=now,
    ).update(
        status=ScrapeJob.STATUS_RUNNING,
        attempts=candidate['attempts'] + 1,
        started_at=now,
        finished_at=None,
        updated_at=now,
    )
    if updated != 1:
        return None
    claimed = ScrapeJob.objects.get(pk=candidate['id'])
    claimed.claimed_from_status = claimed_from_status
    claimed.queue_lane = 'fresh' if claimed_from_status == ScrapeJob.STATUS_PENDING else 'retry'
    return claimed


def _successful_domains_for_query(query: str, limit: int = 20) -> set[str]:
    if not query:
        return set()
    urls = (
        ScrapeJob.objects.filter(query=query, status=ScrapeJob.STATUS_SUCCESS)
        .order_by('-finished_at', '-created_at')
        .values_list('url', flat=True)[:max(1, limit)]
    )
    return {domain_from_url(url) for url in urls if url}


def _queue_priority(job: ScrapeJob, successful_domains: set[str], health_cache: dict[str, float]) -> float:
    domain = domain_from_url(job.url)
    if domain not in health_cache:
        health_cache[domain] = float(url_domain_health_score(job.url))

    product_score = float(product_url_score(job.url, query=job.query))
    health_score = health_cache[domain]
    diversity_bonus = 0.0 if domain in successful_domains else 12.0
    return (product_score * 10.0) + (health_score * 8.0) + diversity_bonus


def _claim_best_from_lane(status: str, now, window: int) -> ScrapeJob | None:
    candidates = list(
        ScrapeJob.objects.filter(status=status, available_at__lte=now)
        .order_by('available_at', 'created_at')[:window]
    )
    if not candidates:
        return None

    successful_domains_by_query = {}
    health_cache = {}
    for job in candidates:
        if job.query not in successful_domains_by_query:
            successful_domains_by_query[job.query] = _successful_domains_for_query(job.query)

    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (
            -_queue_priority(
                item[1],
                successful_domains_by_query[item[1].query],
                health_cache,
            ),
            item[0],
        ),
    )
    for _, candidate in ranked:
        claimed = claim_job(candidate.id)
        if claimed:
            return claimed
    return None


def claim_next_job() -> ScrapeJob | None:
    """Claim fresh jobs first, then retry jobs.

    Pending candidates and retries live in separate logical lanes. Quality, domain
    health and merchant diversity are used within each lane, but a ready retry can
    never jump ahead of a ready fresh candidate.
    """
    now = timezone.now()
    window = max(5, int(getattr(settings, 'SCRAPE_JOB_PRIORITY_WINDOW', 40)))

    for _ in range(5):
        claimed = _claim_best_from_lane(ScrapeJob.STATUS_PENDING, now, window)
        if claimed:
            return claimed
        claimed = _claim_best_from_lane(ScrapeJob.STATUS_RETRY, now, window)
        if claimed:
            return claimed
        return None
    return None


def defer_job(job: ScrapeJob, delay_seconds: int, reason: str = 'domain_cooldown') -> ScrapeJob:
    now = timezone.now()
    job.status = ScrapeJob.STATUS_RETRY
    job.attempts = max(0, int(job.attempts or 0) - 1)
    job.available_at = now + timedelta(seconds=max(1, int(delay_seconds)))
    job.started_at = None
    job.finished_at = now
    job.fetch_status = reason
    job.last_error = 'Traitement différé temporairement.'
    job.save(update_fields=['status', 'attempts', 'available_at', 'started_at', 'finished_at', 'fetch_status', 'last_error', 'updated_at'])
    return job


def complete_job(job: ScrapeJob, listing=None, fetch_status: str = 'success', http_status=None, duration_ms: int = 0, from_cache: bool = False):
    job.status = ScrapeJob.STATUS_SUCCESS
    job.listing = listing
    job.last_error = ''
    job.fetch_status = fetch_status or 'success'
    job.http_status = http_status
    job.duration_ms = max(0, int(duration_ms or 0))
    job.from_cache = bool(from_cache)
    job.finished_at = timezone.now()
    job.save()
    return job


def fail_job(job: ScrapeJob, error: str, *, retryable: bool = False, fetch_status: str = '', http_status=None, duration_ms: int = 0, from_cache: bool = False):
    now = timezone.now()
    can_retry = retryable and job.attempts < job.max_attempts
    job.status = ScrapeJob.STATUS_RETRY if can_retry else ScrapeJob.STATUS_FAILED
    job.last_error = (error or '')[:4000]
    job.fetch_status = fetch_status or ''
    job.http_status = http_status
    job.duration_ms = max(0, int(duration_ms or 0))
    job.from_cache = bool(from_cache)
    job.finished_at = now
    if can_retry:
        delay_seconds = 3 ** max(job.attempts - 1, 0)
        job.available_at = now + timedelta(seconds=delay_seconds)
    job.save()
    return job
