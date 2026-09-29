from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker.models import PriceListing, Product, Retailer, ScrapeJob, SearchRun


class RecentSearchHistoryTests(TestCase):
    def setUp(self):
        self.run = SearchRun.objects.create(
            query='Samsung Galaxy A56 5G 8GB 256GB',
            site_filter='all',
            target_merchants=3,
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_COMPLETED,
            discovery_finished_at=timezone.now(),
            completed_at=timezone.now(),
            discovery_sources=[
                {
                    'url': 'https://www.tiktok.com/@shop/video/123',
                    'platform': 'TikTok',
                    'title': 'Samsung Galaxy A56 5G',
                    'snippet': 'Produit disponible',
                    'relevance_score': 0.9,
                    'source_type': 'Réseau social',
                }
            ],
        )
        product = Product.objects.create(name='Samsung Galaxy A56 5G 8GB 256GB')
        retailer = Retailer.objects.create(
            name='Boutique historique',
            base_url='https://boutique-historique.example',
        )
        listing = PriceListing.objects.create(
            product=product,
            retailer=retailer,
            url='https://boutique-historique.example/product/a56',
            price=Decimal('299.00'),
            currency='USD',
            in_stock=True,
        )
        ScrapeJob.objects.create(
            search_run=self.run,
            query=self.run.query,
            url=listing.url,
            status=ScrapeJob.STATUS_SUCCESS,
            listing=listing,
            finished_at=timezone.now(),
        )

    def test_homepage_shows_recent_search(self):
        response = self.client.get(reverse('scrape_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recherches récentes')
        self.assertContains(response, self.run.query)
        self.assertContains(response, reverse('search_run_detail', args=[self.run.pk]))

    def test_search_history_lists_database_runs(self):
        response = self.client.get(reverse('search_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.run.query)
        self.assertContains(response, '1 offre')
        self.assertContains(response, '1 source')

    def test_search_run_detail_shows_offers_and_discovery_sources(self):
        response = self.client.get(reverse('search_run_detail', args=[self.run.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.run.query)
        self.assertContains(response, 'Boutique historique')
        self.assertContains(response, 'TikTok')
        self.assertContains(response, 'Réseaux sociaux et autres sources')


    def test_search_history_filters_by_product_query(self):
        other = SearchRun.objects.create(
            query='iPhone 16 Pro 256GB',
            site_filter='all',
            target_merchants=3,
            market_code='GLOBAL',
            market_currency='',
            status=SearchRun.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )

        response = self.client.get(reverse('search_history'), {'q': 'Samsung Galaxy'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.run.query)
        self.assertNotContains(response, other.query)
        self.assertContains(response, 'Résultats pour « Samsung Galaxy ».')

    def test_search_history_empty_filter_message(self):
        response = self.client.get(reverse('search_history'), {'q': 'Produit introuvable xyz'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Aucune recherche enregistrée ne correspond à « Produit introuvable xyz ».',
        )
