from django.test import SimpleTestCase

from tracker.listing_discovery import is_discovery_page_url


class ListingDiscoveryTests(SimpleTestCase):
    def test_category_and_search_pages_are_discovery_sources(self):
        urls = [
            "https://www.idealo.fr/cat/3011/disques-durs.html",
            "https://www.fnac.com/Disque-Dur/shi48972/w-4",
            "https://www.amazon.fr/disque-dur/s?k=disque+dur",
            "https://merchant.example/search?q=disque+dur",
            "https://merchant.example/collections/storage",
        ]
        self.assertTrue(all(is_discovery_page_url(url) for url in urls))

    def test_noise_pages_are_not_discovery_sources(self):
        urls = [
            "https://forums.raspberrypi.com/viewtopic.php?t=1",
            "https://merchant.example/policies/privacy-policy",
            "https://merchant.example/blog/best-hard-drive",
            "https://www.bing.com/aclick?ld=test",
            "https://studylib.net/doc/123/test",
        ]
        self.assertTrue(all(not is_discovery_page_url(url) for url in urls))

    def test_product_detail_page_is_not_a_listing_source(self):
        self.assertFalse(is_discovery_page_url(
            "https://merchant.example/products/toshiba-hdd-1tb"
        ))
