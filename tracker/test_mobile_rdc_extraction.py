from django.test import SimpleTestCase

from tracker.extractors import extract_structured_product


class MobileRdcExtractionTests(SimpleTestCase):
    def test_extracts_product_when_h1_is_ellipsis(self):
        html = """
        <html>
          <body>
            <main>
              <h1>…</h1>
              <section class="product type-product">
                <h2>Quel est le prix de l’iPhone 16e à Kinshasa ?</h2>
                <p>La sortie de l’iPhone 16e à Kinshasa propose un excellent rapport qualité-prix.</p>
                <div class="flash-sale">VENTE FLASH</div>
                <div class="price">1000$</div>
                <a href="#whatsapp">Commander sur WhatsApp</a>
              </section>
            </main>
          </body>
        </html>
        """

        result = extract_structured_product(html, query="iPhone 16e")

        self.assertIsNotNone(result)
        self.assertIn("iphone 16e", result.product_name.lower())
        self.assertEqual(float(result.price), 1000.0)
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.source, "html")
