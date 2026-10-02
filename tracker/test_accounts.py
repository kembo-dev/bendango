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
        self.assertContains(first, '?q=Samsung&page=2')

        third = self.client.get(reverse('search_history'), {'q': 'Samsung', 'page': 3})
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.context['searches'].number, 3)
        self.assertEqual(len(third.context['searches'].object_list), 3)
        self.assertContains(third, 'Page 3 sur 3')