import subprocess
import sys
import time
from datetime import timedelta

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

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
            search_run.discovery_error = (
                'Découverte interrompue: SearchRun remis en file après expiration du worker.'
            )
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


def _finalize_hard_timeout(run_id, run_timeout):
    now = timezone.now()
    search_run = SearchRun.objects.get(pk=run_id)
    successful_jobs = search_run.jobs.filter(
        status='success', listing__isnull=False
    ).exists()
    active_jobs = search_run.jobs.filter(
        status__in=['pending', 'running', 'retry']
    )

    # Discovery has stopped permanently, so queued discovery jobs must not keep
    # the SearchRun looking active forever. Running scrape jobs are left to the
    # scrape workers; pending/retry jobs are cancelled by deleting them.
    active_jobs.filter(status__in=['pending', 'retry']).delete()

    if successful_jobs:
        SearchRun.objects.filter(pk=run_id).update(
            status=SearchRun.STATUS_COMPLETED,
            discovery_error='',
            discovery_finished_at=now,
            completed_at=now,
        )
        return 'completed'

    SearchRun.objects.filter(pk=run_id).update(
        status=SearchRun.STATUS_FAILED,
        discovery_error=(
            f'Délai maximal de découverte dépassé ({run_timeout}s).'
        ),
        discovery_finished_at=now,
        completed_at=now,
    )
    return 'failed'


class Command(BaseCommand):
    help = 'Process queued Bendango SearchRun discovery jobs.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--poll-interval', type=float, default=1.0)
        parser.add_argument('--exit-when-empty', action='store_true')
        parser.add_argument('--stale-timeout', type=int, default=None)
        parser.add_argument('--run-timeout', type=int, default=None)

    def _claim_next_run(self):
        with transaction.atomic():
            queryset = SearchRun.objects.filter(
                status=SearchRun.STATUS_QUEUED
            ).order_by('created_at')
            queryset = (
                queryset.select_for_update(skip_locked=True)
                if transaction.get_connection().vendor == 'postgresql'
                else queryset.select_for_update()
            )
            search_run = queryset.first()
            if search_run is None:
                return None
            search_run.status = SearchRun.STATUS_DISCOVERING
            search_run.discovery_started_at = timezone.now()
            search_run.discovery_error = ''
            search_run.save(
                update_fields=[
                    'status',
                    'discovery_started_at',
                    'discovery_error',
                ]
            )
            return search_run

    def _run_direct(self, search_run):
        # Keep --once deterministic and patch-friendly for unit tests.
        call_command('process_search_run', str(search_run.pk))

    def _run_isolated(self, search_run, run_timeout):
        command = [
            sys.executable,
            'manage.py',
            'process_search_run',
            str(search_run.pk),
        ]
        try:
            result = subprocess.run(
                command,
                timeout=run_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            status = _finalize_hard_timeout(search_run.pk, run_timeout)
            return status, True

        search_run.refresh_from_db()
        if result.returncode != 0 and not search_run.completed_at:
            now = timezone.now()
            SearchRun.objects.filter(pk=search_run.pk).update(
                status=SearchRun.STATUS_FAILED,
                discovery_error=(
                    f'Processus de découverte terminé avec le code {result.returncode}.'
                ),
                discovery_finished_at=now,
                completed_at=now,
            )
            return 'failed', False
        return search_run.status, False

    def handle(self, *args, **options):
        recovered = recover_stale_search_runs(options['stale_timeout'])
        if recovered:
            self.stdout.write(
                self.style.WARNING(
                    f'{recovered} stale SearchRun discovery job(s) recovered'
                )
            )

        run_timeout = options['run_timeout']
        if run_timeout is None:
            run_timeout = int(
                getattr(settings, 'SEARCH_RUN_EXECUTION_TIMEOUT', 60)
            )
        run_timeout = max(10, int(run_timeout))
        self.stdout.write(
            self.style.SUCCESS(
                f'Starting Bendango SearchRun discovery worker '
                f'(hard run budget: {run_timeout}s)'
            )
        )

        while True:
            search_run = self._claim_next_run()
            if search_run is None:
                if options['once'] or options['exit_when_empty']:
                    break
                time.sleep(max(options['poll_interval'], 0.1))
                continue

            run_label = str(search_run.pk)[:8]
            self.stdout.write(
                f'run {run_label}: discovery started [{search_run.market_code}]'
            )

            if options['once']:
                try:
                    self._run_direct(search_run)
                    search_run.refresh_from_db()
                    status = search_run.status
                    timed_out = False
                except Exception as exc:
                    now = timezone.now()
                    SearchRun.objects.filter(pk=search_run.pk).update(
                        status=SearchRun.STATUS_FAILED,
                        discovery_error=str(exc),
                        discovery_finished_at=now,
                        completed_at=now,
                    )
                    status = 'failed'
                    timed_out = False
            else:
                status, timed_out = self._run_isolated(search_run, run_timeout)

            if timed_out:
                self.stderr.write(
                    f'run {run_label}: hard discovery timeout after '
                    f'{run_timeout}s ({status})'
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'run {run_label}: discovery complete ({status})'
                    )
                )

            if options['once']:
                break
