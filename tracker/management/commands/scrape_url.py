from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tracker.models import Product, Retailer, PriceListing
from tracker.services import LLMRequiredError, ExtractedProductData, get_llm_model_reference, extract_with_llm


class Command(BaseCommand):
    help = "Scrape une URL produit avec le profil LLM configuré et enregistre en BDD."

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="L'URL de la page produit à scraper")
        parser.add_argument(
            "--model",
            type=str,
            default=None,
            help="Modèle à utiliser (ex: us.meta.llama3-1-70b-instruct-v1:0 pour Bedrock, ou qwen2.5-coder:7b pour Ollama)",
        )

    def handle(self, *args, **options):
        url = options["url"]
        try:
            model_name = options["model"] or get_llm_model_reference()
        except LLMRequiredError as error:
            raise CommandError(str(error)) from None

        self.stdout.write(self.style.NOTICE(f"Début du traitement pour : {url}"))

        # --- ÉTAPE 1 : Fetch & Cleaning du HTML ---
        html_content = self.fetch_clean_html(url)
        if not html_content:
            raise CommandError("Impossible de récupérer ou nettoyer le contenu HTML.")

        # --- ÉTAPE 2 : Extraction structurée avec le profil LLM ---
        self.stdout.write(f"Extraction des données avec le profil LLM ({model_name})...")
        try:
            extracted_data = extract_with_llm(html_content, model_name)
        except LLMRequiredError as error:
            raise CommandError(str(error)) from None

        if not extracted_data:
            raise CommandError("Échec de l'extraction avec le profil LLM.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Données extraites : {extracted_data.product_name} - "
                f"{extracted_data.price} {extracted_data.currency}"
            )
        )

        # --- ÉTAPE 3 : Enregistrement en BDD ---
        self.save_to_database(url, extracted_data)

    def fetch_clean_html(self, url: str) -> str | None:
        """Télécharge la page HTML et filtre le contenu."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"Erreur HTTP : {e}"))
            return None

        soup = BeautifulSoup(response.content, "html.parser")

        for element in soup(["script", "style", "svg", "noscript", "header", "footer", "nav"]):
            element.decompose()

        target = soup.find("body") or soup
        cleaned_html = str(target)

        # Pour les modèles locaux, réduire la taille du contexte aide à la vitesse d'exécution
        return cleaned_html[:80000]

    def save_to_database(self, url: str, data: ExtractedProductData):
        """Enregistre ou met à jour le commerçant, le produit et le relevé de prix."""
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.replace("www.", "")

        with transaction.atomic():
            retailer, _ = Retailer.objects.get_or_create(
                name=domain.capitalize(),
                defaults={"base_url": f"{parsed_url.scheme}://{parsed_url.netloc}"},
            )

            product = None
            if data.sku_or_ean:
                product = Product.objects.filter(sku_or_ean=data.sku_or_ean).first()

            if not product:
                product, _ = Product.objects.get_or_create(
                    name=data.product_name,
                    defaults={"sku_or_ean": data.sku_or_ean},
                )

            listing = PriceListing.objects.create(
                product=product,
                retailer=retailer,
                url=url,
                price=data.price,
                currency=data.currency,
                in_stock=data.in_stock,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Relevé de prix enregistré avec succès (ID: {listing.id}) pour {product.name}!"
                )
            )