import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.adaptive_engine import search_and_scrape_product
from tracker.discovery_sources import discover_social_sources
from tracker.models import SearchRun


def recover_stale_search_runs(timeout_seconds=None):
    """Requeue SearchRun records abandoned while discovery was in progress."""
    if timeout_seconds is None:
        timeout_seconds = int(getattr(settings, 'SEARCH_RUN_DISCOVERY_TIMEOUT', 300))
    cutoff = timezone.now() - timedelta(seconds=max(1, int(timeout_seconds)))
    stale_ids = list(
        SearchRun.objects.filter(
            status=SearchRun.STATUS_DISCOVERING,
            discovery_started_at__isnull=False,
            discovery_started_at__lt=cutoff,
            completed_at__isnull=True,
        ).values_list('id', flat=True)
    )
    recovered = 0
    for run_id in stale_ids:
        with transaction.atomic():
            search_run = SearchRun.objects.filter(
                pk=run_id,
                status=SearchRun.STATUS_DISCOVERING,
                completed_at__isnull=True,
            ).first()
            if search_run is None:
                continue
            search_run.status = SearchRun.STATUS_QUEUED
            search_run.discovery_started_at = None
            search_run.discovery_finished_at = None
            search_run.discovery_error = 'Découverte interrompue: SearchRun remis en file après expiration du worker.'
            search_run.save(
                update_fields=[
                    'status',
                    'discovery_started_at',
                    'discovery_finished_at',
                    'discovery_error',
                ]
            )
            recovered += 1
    return recovered


class Command(BaseCommand):
    help = 'Process queued Bendango SearchRun discovery jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--poll-interval', type=float, default=1.0)
        parser.add_argument('--exit-when-empty', action='store_true')
        parser.add_argument('--stale-timeout', type=int, default=None)

    def _claim_next_run(self):
        with transaction.atomic():
            queryset = SearchRun.objects.filter(status=SearchRun.STATUS_QUEUED).order_by('created_at')
            if transaction.get_connection().vendor == 'postgresql':
                queryset = queryset.select_for_update(skip_locked=True)
            else:
                queryset = queryset.select_for_update()
            search_run = queryset.first()
            if search_run is None:
                return None
            search_run.status = SearchRun.STATUS_DISCOVERING
            search_run.discovery_started_at = timezone.now()
            search_run.discovery_error = ''
            search_run.save(update_fields=['status', 'discovery_started_at', 'discovery_error'])
            return search_run

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting Bendango SearchRun discovery worker'))
        recovered = recover_stale_search_runs(options['stale_timeout'])
        if recovered:
            self.stdout.write(self.style.WARNING(f'{recovered} stale SearchRun discovery job(s) recovered'))
        while True:
            search_run = self._claim_next_run()
            if search_run is None:
                if options['once'] or options['exit_when_empty']:
                    break
                time.sleep(max(options['poll_interval'], 0.1))
                continue

            run_label = str(search_run.pk)[:8]
            try:
                # All external discovery work lives here, never in Gunicorn.
                try:
                    social_sources = discover_social_sources(search_run.query)
                except Exception as exc:
                    social_sources = []
                    self.stderr.write(f'run {run_label}: social discovery warning - {exc}')

                search_run.discovery_sources = social_sources
                search_run.save(update_fields=['discovery_sources'])

                search_and_scrape_product(
                    product_query=search_run.query,
                    site_filter=search_run.site_filter,
                    model_name=search_run.model_name or None,
                    search_run=search_run,
                )

                search_run.refresh_from_db()
                search_run.discovery_finished_at = timezone.now()
                active_jobs = search_run.jobs.filter(status__in=['pending', 'running', 'retry']).exists()
                successful_jobs = search_run.jobs.filter(status='success', listing__isnull=False).exists()
                if search_run.completed_at:
                    search_run.status = SearchRun.STATUS_COMPLETED
                elif active_jobs:
                    search_run.status = SearchRun.STATUS_RUNNING
                elif successful_jobs:
                    search_run.status = SearchRun.STATUS_COMPLETED
                    search_run.completed_at = timezone.now()
                else:
                    search_run.status = SearchRun.STATUS_FAILED
                    search_run.discovery_error = 'Aucune page marchande exploitable n’a été trouvée.'
                    search_run.completed_at = timezone.now()
                search_run.save(update_fields=['status', 'discovery_finished_at', 'discovery_error', 'completed_at'])
                self.stdout.write(self.style.SUCCESS(f'run {run_label}: discovery complete ({search_run.status})'))
            except Exception as exc:
                SearchRun.objects.filter(pk=search_run.pk).update(
                    status=SearchRun.STATUS_FAILED,
                    discovery_error=str(exc),
                    discovery_finished_at=timezone.now(),
                    completed_at=timezone.now(),
                )
                self.stderr.write(f'run {run_label}: discovery failed - {exc}')

            if options['once']:
                break
