from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from tracker.models import SearchRun


class ProcessSearchRunOrderTests(TestCase):
    def test_merchant_discovery_runs_before_social_enrichment(self):
        run = SearchRun.objects.create(
            query='string femme',
            site_filter='all',
            target_merchants=3,
            model_name='test-model',
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_DISCOVERING,
        )
        phases = []

        def fake_search(*args, **kwargs):
            phases.append('merchant')
            return [], []

        def fake_social(*args, **kwargs):
            phases.append('social')
            return []

        with patch(
            'tracker.management.commands.process_search_run.search_and_scrape_product',
            side_effect=fake_search,
        ), patch(
            'tracker.management.commands.process_search_run.discover_social_sources',
            side_effect=fake_social,
        ):
            call_command('process_search_run', str(run.pk))

        self.assertEqual(phases, ['merchant', 'social'])
