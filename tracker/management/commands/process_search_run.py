import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tracker.discovery_sources import discover_social_sources, discovery_sources_to_json
from tracker.models import SearchRun


class Command(BaseCommand):
    help = 'Process one already-claimed SearchRun in an isolated process.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')

    def handle(self, *args, **options):
        run_id = options['run_id']
        try:
            search_run = SearchRun.objects.get(pk=run_id)
        except SearchRun.DoesNotExist as exc:
            raise CommandError(f'SearchRun {run_id} introuvable.') from exc

        run_label = str(search_run.pk)[:8]
        try:
            self.stdout.write(f'run {run_label}: merchant discovery phase started')
            merchant_timeout = max(1, int(getattr(settings, 'SEARCH_RUN_MERCHANT_TIMEOUT', 45)))
            if getattr(settings, 'TESTING', False):
                # Test DBs may be in-memory and cannot safely be shared with a
                # nested OS process. Production still gets the hard child cap.
                call_command('process_merchant_search', str(search_run.pk))
                self.stdout.write(f'run {run_label}: merchant discovery phase finished')
            else:
                manage_py = str(Path(settings.BASE_DIR) / 'manage.py')
                try:
                    subprocess.run(
                        [sys.executable, manage_py, 'process_merchant_search', str(search_run.pk)],
                        cwd=str(settings.BASE_DIR),
                        timeout=merchant_timeout,
                        check=False,
                    )
                    self.stdout.write(f'run {run_label}: merchant discovery phase finished')
                except subprocess.TimeoutExpired:
                    self.stdout.write(self.style.WARNING(
                        f'run {run_label}: merchant discovery budget reached after {merchant_timeout}s; preserving partial coverage'
                    ))

            self.stdout.write(f'run {run_label}: social enrichment phase started')
            try:
                social_sources = discover_social_sources(search_run.query, market_code=search_run.market_code)
            except Exception as exc:
                social_sources = []
                self.stderr.write(f'run {run_label}: social discovery warning - {exc}')
            search_run.discovery_sources = discovery_sources_to_json(social_sources)
            search_run.save(update_fields=['discovery_sources'])
            self.stdout.write(f'run {run_label}: social enrichment phase finished')

            search_run.refresh_from_db()
            now = timezone.now()
            active_jobs = search_run.jobs.filter(status__in=['pending', 'running', 'retry']).exists()
            successful_jobs = search_run.jobs.filter(status='success', listing__isnull=False).exists()
            search_run.discovery_finished_at = now
            if search_run.completed_at:
                search_run.status = SearchRun.STATUS_COMPLETED
            elif active_jobs:
                search_run.status = SearchRun.STATUS_RUNNING
            elif successful_jobs:
                search_run.status = SearchRun.STATUS_COMPLETED; search_run.completed_at = now
            else:
                search_run.status = SearchRun.STATUS_FAILED; search_run.discovery_error = 'Aucune page marchande exploitable n’a été trouvée.'; search_run.completed_at = now
            search_run.save(update_fields=['status', 'discovery_finished_at', 'discovery_error', 'completed_at'])
        except Exception as exc:
            now = timezone.now()
            SearchRun.objects.filter(pk=search_run.pk).update(status=SearchRun.STATUS_FAILED, discovery_error=str(exc), discovery_finished_at=now, completed_at=now)
            raise
