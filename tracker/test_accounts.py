from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from tracker.models import BusinessAccountRequest, SearchRun


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
