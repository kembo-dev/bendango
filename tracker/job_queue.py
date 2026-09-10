from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from tracker.models import ScrapeJob


ACTIVE_STATUSES = (ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY, ScrapeJob.STATUS_RUNNING)
CLAIMABLE_STATUSES = (ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RETRY)


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
    """Atomically claim one specific job if it is still available."""
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
    return ScrapeJob.objects.get(pk=candidate['id'])


def claim_next_job() -> ScrapeJob | None:
    """Atomically claim one available job without double-claiming across workers."""
    now = timezone.now()
    for _ in range(5):
        candidate = (
            ScrapeJob.objects.filter(
                status__in=CLAIMABLE_STATUSES,
                available_at__lte=now,
            )
            .order_by('available_at', 'created_at')
            .values('id')
            .first()
        )
        if not candidate:
            return None
        claimed = claim_job(candidate['id'])
        if claimed:
            return claimed
    return None


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
