from django.test import SimpleTestCase

from tracker.candidate_filter import filter_and_rank_candidate_urls, is_low_value_candidate_url


class CandidateFilterTests(SimpleTestCase):
    def test_rejects_category_and_search_pages(self):
        urls = [
            "https://www.idealo.fr/cat/3011/disques-durs.html",
            "https://www.fnac.com/Disque-Dur/shi48972/w-4",
            "https://www.amazon.fr/disque-dur/s?k=disque+dur",
            "https://www.cdiscount.com/informatique/r-disque+dur+hdd.html?search=1",
        ]
        self.assertTrue(all(is_low_value_candidate_url(url) for url in urls))

    def test_rejects_policy_forum_and_search_engine_ad_urls(self):
        urls = [
            "https://floraciccarelli.com/policies/privacy-policy",
            "https://forums.raspberrypi.com/viewtopic.php",
            "https://www.techguy.org/threads/hard-drive.123/",
            "https://www.bing.com/aclick?ld=test",
            "https://studylib.net/doc/123/test",
        ]
        self.assertTrue(all(is_low_value_candidate_url(url) for url in urls))

    def test_keeps_real_product_detail_pages(self):
        urls = [
            "https://boutique.likonzi.com/disque-dur-externe-toshiba-1tb-1to/yMYer022bOB",
            "https://kindinformatique.com/products/disque-dur-ssd-kingspec-p3-1tb-2-5-sata",
            "https://www.oui.cd/product/kinshasa-pc11-kalamu-a115-disque-dur-1tb",
        ]
        self.assertTrue(all(not is_low_value_candidate_url(url) for url in urls))

    def test_product_pages_are_ranked_before_ambiguous_pages(self):
        ambiguous = "https://merchant.example/hardware/storage"
        product = "https://merchant.example/products/toshiba-hdd-1tb"
        ranked = filter_and_rank_candidate_urls([ambiguous, product])
        self.assertEqual(ranked[0], product)

    def test_broad_query_rejects_editorial_pages_before_queue(self):
        urls = [
            "https://www.guitare-tabs.eu/guitare",
            "https://www.apprendrelaguitare.fr/cours/debutant",
            "https://merchant.example/products/guitare-yamaha-c40",
        ]
        ranked = filter_and_rank_candidate_urls(urls, query="guitare")
        self.assertEqual(ranked, ["https://merchant.example/products/guitare-yamaha-c40"])

    def test_broad_query_keeps_unknown_merchant_product_page(self):
        url = "https://nouvelle-boutique.cd/products/guitare-acoustique"
        self.assertFalse(is_low_value_candidate_url(url, query="guitare"))

    def test_precise_model_query_does_not_overfilter_ambiguous_product_url(self):
        url = "https://merchant.example/catalogue/iphone-16e-256gb"
        self.assertFalse(is_low_value_candidate_url(url, query="iPhone 16e 256GB"))

    def test_query_overlap_improves_candidate_ranking(self):
        matching = "https://merchant.example/shop/guitare-yamaha-c40"
        generic = "https://merchant.example/shop/accessoire-musique"
        ranked = filter_and_rank_candidate_urls([generic, matching], query="guitare")
        self.assertEqual(ranked[0], matching)
