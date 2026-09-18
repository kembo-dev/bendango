from django.core.management.base import BaseCommand, CommandError

from tracker.discovery_sources import discover_social_sources, discovery_sources_to_json
from tracker.models import SearchRun


class Command(BaseCommand):
    help = 'Run only social/comparison discovery for an already-claimed SearchRun.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')

    def handle(self, *args, **options):
        try:
            search_run = SearchRun.objects.get(pk=options['run_id'])
        except SearchRun.DoesNotExist as exc:
            raise CommandError(f"SearchRun {options['run_id']} introuvable.") from exc

        try:
            social_sources = discover_social_sources(
                search_run.query,
                market_code=search_run.market_code,
            )
        except Exception as exc:
            self.stderr.write(
                f'run {str(search_run.pk)[:8]}: social discovery warning - {exc}'
            )
            social_sources = []

        search_run.discovery_sources = discovery_sources_to_json(social_sources)
        search_run.save(update_fields=['discovery_sources'])
