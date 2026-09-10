from django.test import SimpleTestCase

from tracker.job_outcomes import classify_processing_error


class JobOutcomeClassificationTests(SimpleTestCase):
    def test_classifies_known_processing_failures(self):
        cases = [
            ('Impossible de récupérer le contenu de la page web.', ('fetch_failed', True)),
            ('Page sans structure de produit exploitable.', ('no_product_structure', False)),
            ('Produit non pertinent pour la recherche.', ('product_mismatch', False)),
            ('Données extraites invalides.', ('invalid_data', False)),
            ('Source non marchande ignorée.', ('non_merchant', False)),
            ('Protection anti-bot détectée', ('anti_bot', True)),
        ]
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(classify_processing_error(message), expected)

    def test_unknown_failure_keeps_generic_category(self):
        self.assertEqual(classify_processing_error('Erreur métier inconnue'), ('processing_failure', False))
