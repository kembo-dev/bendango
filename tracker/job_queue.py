from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from tracker.models import ScrapeJob


ACTIVE_STATUSES = (ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY, ScrapeJob.STATUS_RUNNING)


def enqueue_scrape_job(url: str, query: str = '', model_name: str = '', max_attempts: int = 3) -> ScrapeJob:
    """Create work unless the same URL/query already has an active job."""
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


def claim_next_job() -> ScrapeJob | None:
    """Atomically claim one available pending/retry job."""
    now = timezone.now()
    with transaction.atomic():
        job = (
            ScrapeJob.objects.select_for_update()
            .filter(status__in=[ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY], available_at__lte=now)
            .order_by('available_at', 'created_at')
            .first()
        )
        if not job:
            return None
        job.status = ScrapeJob.STATUS_RUNNING
        job.attempts += 1
        job.started_at = now
        job.finished_at = None
        job.save(update_fields=['status', 'attempts', 'started_at', 'finished_at', 'updated_at'])
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
