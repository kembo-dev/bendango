from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BusinessAccountRequest, BusinessProfile, Offer, OfferBoostRequest, SearchRun


class HomepageDiscoveryFeedTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            username='feedowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=owner,
            business_name='Feed Business',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.profile = BusinessProfile.objects.get(user=owner)
        self.profile.city = 'Kinshasa'
        self.profile.market_code = 'CD'
        self.profile.save(update_fields=['city', 'market_code'])

    def test_homepage_shows_published_offers_and_community_searches(self):
        Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Aquafina 500ml',
            price='1.50',
            currency='USD',
            market_code='CD',
        )
        searcher = User.objects.create_user(
            username='private-searcher-name',
            password='StrongPass123!',
        )
        SearchRun.objects.create(
            user=searcher,
            query='Samsung Galaxy A56 8GB 256GB',
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_COMPLETED,
        )

        response = self.client.get(reverse('scrape_view'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Les annonces du marché')
        self.assertContains(response, 'Aquafina 500ml')
        self.assertContains(response, 'Pro validé')
        self.assertContains(response, 'Samsung Galaxy A56 8GB 256GB')
        self.assertContains(response, 'Recherché récemment')
        self.assertNotContains(response, 'private-searcher-name')

    def test_homepage_discovery_feed_is_paginated(self):
        for index in range(7):
            Offer.objects.create(
                business=self.profile,
                offer_type='product',
                title=f'Produit Bendango {index}',
                price='10.00',
                currency='USD',
                market_code='CD',
            )
        for index in range(7):
            SearchRun.objects.create(
                query=f'Produit recherché {index}',
                market_code='CD',
                market_currency='CDF',
                status=SearchRun.STATUS_COMPLETED,
            )

        first = self.client.get(reverse('scrape_view'))
        page = first.context['discovery_page']

        self.assertEqual(first.status_code, 200)
        self.assertEqual(page.paginator.count, 14)
        self.assertEqual(len(page.object_list), 12)
        self.assertTrue(page.has_next())
        self.assertContains(first, 'Page 1 sur 2')
        self.assertContains(first, '?page=2')

        second = self.client.get(reverse('scrape_view'), {'page': 2})
        second_page = second.context['discovery_page']

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second_page.number, 2)
        self.assertEqual(len(second_page.object_list), 2)
        self.assertContains(second, 'Page 2 sur 2')

    def test_marketplace_empty_state_and_category_browsing_do_not_consume_trial(self):
        self.assertContains(self.client.get(reverse('scrape_view')), 'Le marché vous attend.')
        Offer.objects.create(business=self.profile, title='Produit du marché', offer_type='product')
        Offer.objects.create(business=self.profile, title='Service du marché', offer_type='service')
        SearchRun.objects.create(query='Sujet de la communauté')
        response = self.client.get(reverse('scrape_view'), {'browse_type': 'service'})
        self.assertContains(response, 'Service du marché')
        self.assertNotContains(response, 'Produit du marché')
        self.assertNotContains(response, 'Sujet de la communauté')
        self.assertEqual(SearchRun.objects.count(), 1)
        self.assertFalse(self.client.session.get('anonymous_search_used', False))
        self.assertContains(self.client.get(reverse('scrape_view'), {'browse_type': 'accommodation'}), 'Ce rayon attend ses prochaines annonces.')

    def test_seller_filters_respect_individual_priority_and_public_visibility(self):
        Offer.objects.create(business=self.profile, title='Offre validée')
        individual = BusinessProfile.objects.create(user=User.objects.create_user(username='browse-individual'),
            business_name='Individuel', is_individual=True, is_verified=True)
        pending = BusinessProfile.objects.create(user=User.objects.create_user(username='browse-pending'),
            business_name='Non validé', is_verified=False)
        Offer.objects.create(business=individual, title='Offre particulière')
        Offer.objects.create(business=pending, title='Offre non validée')
        Offer.objects.create(business=pending, title='Offre cachée', is_public=False)
        for seller, expected in [('individual', 'Offre particulière'), ('pro_verified', 'Offre validée'), ('pro_unverified', 'Offre non validée')]:
            response = self.client.get(reverse('scrape_view'), {'seller': seller})
            self.assertEqual([item['title'] for item in response.context['market_offers']], [expected])
            self.assertNotContains(response, 'Offre cachée')

    def test_browse_filters_combine_and_survive_pagination(self):
        for index in range(13):
            Offer.objects.create(business=self.profile, title=f'Service Paris {index}', offer_type='service', city='Paris', market_code='FR')
        Offer.objects.create(business=self.profile, title='Service ailleurs', offer_type='service', city='Lyon', market_code='FR')
        params = {'browse_type': 'service', 'seller': 'pro_verified', 'browse_market': 'FR', 'browse_city': 'Paris'}
        response = self.client.get(reverse('scrape_view'), params)
        self.assertEqual(response.context['market_offer_count'], 13)
        self.assertContains(response, 'browse_type=service&amp;seller=pro_verified&amp;browse_market=FR&amp;browse_city=Paris&amp;page=2')
        second = self.client.get(reverse('scrape_view'), {**params, 'page': 2})
        self.assertEqual(len(second.context['market_offers']), 1)
        self.assertNotContains(second, 'Service ailleurs')

    def test_invalid_browse_options_are_ignored(self):
        Offer.objects.create(business=self.profile, title='Offre du marché')
        response = self.client.get(reverse('scrape_view'), {'browse_type': 'unknown', 'seller': 'unknown', 'browse_market': 'unknown'})
        self.assertFalse(response.context['browse_filtered'])
        self.assertContains(response, 'Offre du marché')

    def test_publication_origin_distinguishes_pro_status_and_individual(self):
        profiles = [(self.profile, 'pro_verified', 'Pro validé')]
        for username, individual, verified, kind, label in (
            ('pending-pro', False, False, 'pro_unverified', 'Pro non validé'),
            ('private-seller', True, False, 'individual', 'Particulier'),
        ):
            profile = BusinessProfile.objects.create(user=User.objects.create_user(username=username),
                business_name=username, is_individual=individual, is_verified=verified)
            profiles.append((profile, kind, label))
        for profile, kind, label in profiles:
            Offer.objects.create(business=profile, title=f'Annonce de {profile.business_name}')
        response = self.client.get(reverse('scrape_view'))
        items = {item['provider']: item for item in response.context['discovery_page'] if item['kind'] == 'offer'}
        for profile, kind, label in profiles:
            self.assertEqual(items[profile.business_name]['publication_origin']['kind'], kind)
            self.assertContains(response, f'data-publication-origin="{kind}"')
            self.assertContains(response, label)
            offer = Offer.objects.get(business=profile)
            detail = self.client.get(reverse('public_offer', args=[offer.slug]))
            self.assertContains(detail, f'data-publication-origin="{kind}"')
            self.assertContains(detail, label)

    def test_individual_flag_never_displays_a_pro_validation(self):
        self.profile.is_individual = True
        self.profile.save(update_fields=['is_individual'])
        Offer.objects.create(business=self.profile, title='Particulier avec ancien statut')
        response = self.client.get(reverse('scrape_view'))
        self.assertContains(response, 'data-publication-origin="individual"')
        self.assertNotContains(response, 'data-publication-origin="pro_verified"')

    def test_revoked_validation_changes_existing_publication_badge(self):
        offer = Offer.objects.create(business=self.profile, title='Annonce déjà publiée')
        self.assertContains(self.client.get(reverse('scrape_view')), 'data-publication-origin="pro_verified"')
        account_request = BusinessAccountRequest.objects.get(user=self.profile.user)
        account_request.status = BusinessAccountRequest.STATUS_REJECTED
        account_request.save()
        response = self.client.get(reverse('scrape_view'))
        self.assertContains(response, offer.title)
        self.assertContains(response, 'data-publication-origin="pro_unverified"')
        self.assertNotContains(response, 'data-publication-origin="pro_verified"')

    def test_search_topics_do_not_receive_a_seller_status(self):
        SearchRun.objects.create(query='Sujet communautaire', market_code='CD')
        response = self.client.get(reverse('scrape_view'))
        item = response.context['discovery_page'].object_list[0]
        self.assertEqual(item['kind'], 'search')
        self.assertNotIn('publication_origin', item)
        self.assertNotContains(response, 'data-publication-origin=')

    def test_duplicate_public_search_topics_are_collapsed(self):
        SearchRun.objects.create(
            query='iPhone 16 Pro 256GB',
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_COMPLETED,
        )
        SearchRun.objects.create(
            query='IPHONE 16 PRO 256GB',
            market_code='CD',
            market_currency='CDF',
            status=SearchRun.STATUS_COMPLETED,
        )

        response = self.client.get(reverse('scrape_view'))
        search_items = [
            item for item in response.context['discovery_page'].paginator.object_list
            if item['kind'] == 'search'
        ]

        self.assertEqual(len(search_items), 1)
        self.assertEqual(search_items[0]['market_code'], 'CD')

    def test_private_or_inactive_offer_is_not_in_public_feed(self):
        public_offer = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Produit visible',
            price='10.00',
            currency='USD',
        )
        hidden_offer = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Produit caché',
            price='20.00',
            currency='USD',
            is_public=False,
        )

        response = self.client.get(reverse('scrape_view'))

        self.assertContains(response, public_offer.title)
        self.assertNotContains(response, hidden_offer.title)


    def test_boosted_product_is_prioritized_and_labeled_in_home_discovery(self):
        normal = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Produit normal',
            price='10.00',
            currency='USD',
            market_code='CD',
        )
        boosted = Offer.objects.create(
            business=self.profile,
            offer_type='product',
            title='Produit boosté',
            price='20.00',
            currency='USD',
            market_code='CD',
        )
        boost = OfferBoostRequest.objects.create(
            offer=boosted,
            requested_by=self.profile.user,
            duration_days=7,
        )
        boost.approve()

        response = self.client.get(reverse('scrape_view'))
        items = list(response.context['discovery_page'].paginator.object_list)

        offer_items = [item for item in items if item['kind'] == 'offer']
        self.assertEqual(offer_items[0]['title'], boosted.title)
        self.assertTrue(offer_items[0]['promoted'])
        self.assertContains(response, 'Sponsorisé')
        self.assertIn(normal.title, [item['title'] for item in offer_items])
