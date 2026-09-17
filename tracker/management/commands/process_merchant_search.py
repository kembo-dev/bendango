from django.core.management.base import BaseCommand, CommandError

from tracker.adaptive_engine import search_and_scrape_product
from tracker.models import SearchRun


class Command(BaseCommand):
    help = 'Run only merchant discovery for an already-claimed SearchRun.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')

    def handle(self, *args, **options):
        try:
            search_run = SearchRun.objects.get(pk=options['run_id'])
        except SearchRun.DoesNotExist as exc:
            raise CommandError(f"SearchRun {options['run_id']} introuvable.") from exc

        search_and_scrape_product(
            product_query=search_run.query,
            site_filter=search_run.site_filter,
            model_name=search_run.model_name or None,
            search_run=search_run,
            market_code=search_run.market_code,
        )
