from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BusinessAccountRequest, BusinessProfile, SearchRun


class AccountWorkflowTests(TestCase):
    def test_user_can_create_account_and_is_logged_in(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertRedirects(response, reverse('scrape_view'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        follow = self.client.get(reverse('scrape_view'))
        self.assertContains(follow, 'Bonjour newuser')

    def test_authenticated_search_is_owned_by_user(self):
        user = User.objects.create_user(
            username='owner',
            password='StrongPass123!',
        )
        self.client.login(username='owner', password='StrongPass123!')

        response = self.client.post(reverse('scrape_view'), {
            'site': '',
            'query': 'Samsung Galaxy A56 5G 8GB 256GB',
            'market': 'CD',
            'model_name': 'test-model',
        })

        self.assertEqual(response.status_code, 302)
        run = SearchRun.objects.latest('created_at')
        self.assertEqual(run.user, user)

    def test_anonymous_search_remains_supported(self):
        response = self.client.post(reverse('scrape_view'), {
            'site': '',
            'query': 'Samsung Galaxy A56 5G 8GB 256GB',
            'market': 'CD',
            'model_name': 'test-model',
        })

        self.assertEqual(response.status_code, 302)
        run = SearchRun.objects.latest('created_at')
        self.assertIsNone(run.user)

    def test_login_required_for_history(self):
        response = self.client.get(reverse('search_history'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_user_can_submit_business_pro_request(self):
        user = User.objects.create_user(
            username='businessowner',
            password='StrongPass123!',
        )
        self.client.login(username='businessowner', password='StrongPass123!')

        response = self.client.post(reverse('business_account_request'), {
            'business_name': 'Kembo Corporation',
            'business_type': 'E-commerce',
            'website': 'https://kembo.example',
            'phone': '+243000000000',
            'description': 'Nous souhaitons un compte professionnel.',
        })

        self.assertRedirects(response, reverse('business_account_request'))
        request = BusinessAccountRequest.objects.get(user=user)
        self.assertEqual(request.business_name, 'Kembo Corporation')
        self.assertEqual(request.status, BusinessAccountRequest.STATUS_PENDING)

    def test_anonymous_user_cannot_submit_business_request(self):
        response = self.client.get(reverse('business_account_request'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


    def test_duplicate_active_pro_request_is_not_created(self):
        user = User.objects.create_user(
            username='proowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=user,
            business_name='Business One',
            status=BusinessAccountRequest.STATUS_PENDING,
        )
        self.client.login(username='proowner', password='StrongPass123!')

        response = self.client.post(reverse('business_account_request'), {
            'business_name': 'Business Two',
            'business_type': 'Retail',
            'website': '',
            'phone': '',
            'description': 'Deuxième demande',
        })

        self.assertRedirects(response, reverse('business_account_request'))
        self.assertEqual(
            BusinessAccountRequest.objects.filter(user=user).count(),
            1,
        )

    def test_duplicate_email_is_rejected_at_signup(self):
        User.objects.create_user(
            username='existing',
            email='same@example.com',
            password='StrongPass123!',
        )

        response = self.client.post(reverse('signup'), {
            'username': 'another',
            'email': 'SAME@example.com',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Un compte utilise déjà cette adresse e-mail.')
        self.assertFalse(User.objects.filter(username='another').exists())


    def test_approved_request_activates_business_profile(self):
        user = User.objects.create_user(
            username='approvedowner',
            password='StrongPass123!',
        )
        request = BusinessAccountRequest.objects.create(
            user=user,
            business_name='Approved Business',
            business_type='Commerce',
            website='https://approved.example',
            phone='+243111111111',
            description='Business approuvé.',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )

        profile = BusinessProfile.objects.get(user=user)
        self.assertEqual(profile.business_name, 'Approved Business')
        self.assertTrue(profile.is_verified)
        self.assertEqual(profile.approved_request, request)

    def test_pro_dashboard_requires_approved_profile(self):
        user = User.objects.create_user(
            username='pendingowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=user,
            business_name='Pending Business',
            status=BusinessAccountRequest.STATUS_PENDING,
        )
        self.client.login(username='pendingowner', password='StrongPass123!')

        response = self.client.get(reverse('pro_dashboard'))

        self.assertRedirects(response, reverse('business_account_request'))

    def test_approved_user_can_open_and_update_pro_dashboard(self):
        user = User.objects.create_user(
            username='dashboardowner',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=user,
            business_name='Dashboard Business',
            business_type='E-commerce',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.client.login(username='dashboardowner', password='StrongPass123!')

        response = self.client.get(reverse('pro_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard Business')
        self.assertContains(response, 'Compte Pro actif')

        response = self.client.post(reverse('pro_dashboard'), {
            'business_name': 'Dashboard Business RDC',
            'business_type': 'Distribution',
            'website': 'https://dashboard.example',
            'phone': '+243222222222',
            'country': 'RDC',
            'market_code': 'CD',
            'address': 'Kinshasa',
            'logo_url': 'https://dashboard.example/logo.png',
            'description': 'Profil professionnel mis à jour.',
        })

        self.assertRedirects(response, reverse('pro_dashboard'))
        profile = BusinessProfile.objects.get(user=user)
        self.assertEqual(profile.business_name, 'Dashboard Business RDC')
        self.assertEqual(profile.country, 'RDC')
        self.assertEqual(profile.address, 'Kinshasa')

    def test_homepage_shows_pro_dashboard_for_activated_business(self):
        user = User.objects.create_user(
            username='homepro',
            password='StrongPass123!',
        )
        BusinessAccountRequest.objects.create(
            user=user,
            business_name='Home Pro Business',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        self.client.login(username='homepro', password='StrongPass123!')

        response = self.client.get(reverse('scrape_view'))

        self.assertContains(response, 'Espace Pro')
        self.assertContains(response, reverse('pro_dashboard'))


    def test_rejected_request_revokes_verified_profile(self):
        user = User.objects.create_user(
            username='revokedowner',
            password='StrongPass123!',
        )
        request = BusinessAccountRequest.objects.create(
            user=user,
            business_name='Revoked Business',
            status=BusinessAccountRequest.STATUS_APPROVED,
        )
        profile = BusinessProfile.objects.get(user=user)
        self.assertTrue(profile.is_verified)

        request.status = BusinessAccountRequest.STATUS_REJECTED
        request.save(update_fields=['status'])
        profile.refresh_from_db()

        self.assertFalse(profile.is_verified)


    def test_anonymous_user_gets_only_one_search_per_session(self):
        first = self.client.post(reverse('scrape_view'), {
            'site': '',
            'query': 'Samsung Galaxy A56 5G 8GB 256GB',
            'market': 'CD',
            'model_name': 'test-model',
        })

        self.assertEqual(first.status_code, 302)
        self.assertEqual(SearchRun.objects.filter(user__isnull=True).count(), 1)
        session = self.client.session
        self.assertTrue(session.get('anonymous_search_used'))

        second = self.client.post(reverse('scrape_view'), {
            'site': '',
            'query': 'iPhone 16 Pro 256GB',
            'market': 'GLOBAL',
            'model_name': 'test-model',
        })

        self.assertRedirects(second, reverse('signup'))
        self.assertEqual(SearchRun.objects.filter(user__isnull=True).count(), 1)

    def test_authenticated_user_is_not_limited_by_anonymous_trial(self):
        user = User.objects.create_user(
            username='unlimited',
            password='StrongPass123!',
        )
        self.client.login(username='unlimited', password='StrongPass123!')

        for query in ('Samsung Galaxy A56', 'iPhone 16 Pro'):
            response = self.client.post(reverse('scrape_view'), {
                'site': '',
                'query': query,
                'market': 'CD',
                'model_name': 'test-model',
            })
            self.assertEqual(response.status_code, 302)

        self.assertEqual(SearchRun.objects.filter(user=user).count(), 2)

    def test_homepage_explains_anonymous_trial_limit(self):
        response = self.client.get(reverse('scrape_view'))
        self.assertContains(response, '1 recherche gratuite sans compte.')

        session = self.client.session
        session['anonymous_search_used'] = True
        session.save()

        response = self.client.get(reverse('scrape_view'))
        self.assertContains(response, 'Votre recherche gratuite a déjà été utilisée.')
        self.assertContains(response, 'Créer un compte')
        self.assertContains(response, 'Se connecter')


    def test_search_history_is_paginated_and_preserves_filter(self):
        user = User.objects.create_user(
            username='historypager',
            password='StrongPass123!',
        )
        self.client.login(username='historypager', password='StrongPass123!')

        for index in range(27):
            SearchRun.objects.create(
                user=user,
                query=f'Samsung Galaxy A56 recherche {index}',
                market_code='CD',
                market_currency='CDF',
                status=SearchRun.STATUS_COMPLETED,
            )

        first = self.client.get(reverse('search_history'), {'q': 'Samsung'})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.context['searches'].paginator.count, 27)
        self.assertEqual(first.context['searches'].paginator.per_page, 12)
        self.assertEqual(first.context['searches'].number, 1)
        self.assertEqual(len(first.context['searches'].object_list), 12)
        self.assertContains(first, 'Page 1 sur 3')
        self.assertContains(first, '?q=Samsung&amp;page=2')

        third = self.client.get(reverse('search_history'), {'q': 'Samsung', 'page': 3})
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.context['searches'].number, 3)
        self.assertEqual(len(third.context['searches'].object_list), 3)
        self.assertContains(third, 'Page 3 sur 3')
