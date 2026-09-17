from django.template.loader import render_to_string
from django.test import SimpleTestCase

from tracker.discovery_sources import discovery_sources_to_json, source_type_for_platform


class DiscoverySourceTypeTests(SimpleTestCase):
    def test_platforms_are_classified_for_ui(self):
        self.assertEqual(source_type_for_platform("TikTok"), "Réseau social")
        self.assertEqual(source_type_for_platform("Idealo"), "Comparateur")
        self.assertEqual(source_type_for_platform("Les Numériques"), "Fiche informative")
        self.assertEqual(source_type_for_platform("Inconnu"), "Autre source")

    def test_legacy_source_dict_receives_source_type(self):
        data = discovery_sources_to_json([
            {
                "url": "https://www.idealo.fr/prix/test.html",
                "platform": "Idealo",
                "title": "Produit test",
                "snippet": "",
                "relevance_score": 0.9,
            }
        ])
        self.assertEqual(data[0]["source_type"], "Comparateur")

    def test_template_renders_discovery_type_badges(self):
        html = render_to_string(
            "tracker/scrape.html",
            {
                "form": None,
                "listings": [],
                "discovery_sources": [
                    {
                        "url": "https://www.tiktok.com/@test/video/1",
                        "platform": "TikTok",
                        "title": "PS4 à Kinshasa",
                        "snippet": "Prix et livraison",
                        "relevance_score": 1.0,
                        "source_type": "Réseau social",
                    },
                    {
                        "url": "https://www.idealo.fr/prix/test.html",
                        "platform": "Idealo",
                        "title": "Comparatif PS4",
                        "snippet": "Comparatif",
                        "relevance_score": 0.9,
                        "source_type": "Comparateur",
                    },
                ],
                "errors": [],
                "summary": {},
                "async_waiting": False,
                "async_active_jobs": 0,
                "search_run": None,
                "run_state": None,
            },
        )

        self.assertIn("Réseau social", html)
        self.assertIn("Comparateur", html)
        self.assertIn("Pertinence 1,00", html)
