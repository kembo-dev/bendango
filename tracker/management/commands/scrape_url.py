from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import ollama
from pydantic import BaseModel, Field

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tracker.models import Product, Retailer, PriceListing


# 1. Définition du schéma de sortie Pydantic (inchangé)
class ExtractedProductData(BaseModel):
    product_name: str = Field(
        description="Nom complet du produit tel qu'affiché sur la page"
    )
    price: float = Field(
        description="Prix actuel du produit sous forme de nombre flottant sans le symbole monétaire"
    )
    currency: str = Field(
        description="Code ISO de la devise (ex: EUR, USD, CDF)"
    )
    in_stock: bool = Field(
        description="True si le produit est disponible en stock, False sinon"
    )
    sku_or_ean: str | None = Field(
        default=None,
        description="Code SKU, EAN, UPC ou référence unique du produit si disponible",
    )


class Command(BaseCommand):
    help = "Scrape une URL produit, extrait les données avec Ollama en local et enregistre en BDD."

    def add_arguments(self, parser):
        parser.add_argument("url", type=str, help="L'URL de la page produit à scraper")
        parser.add_argument(
            "--model",
            type=str,
            default="qwen2.5-coder:7b",
            help="Modèle Ollama à utiliser (par défaut: qwen2.5-coder:7b)",
        )

    def handle(self, *args, **options):
        url = options["url"]
        model_name = options["model"]

        self.stdout.write(self.style.NOTICE(f"Début du traitement pour : {url}"))

        # --- ÉTAPE 1 : Fetch & Cleaning du HTML ---
        html_content = self.fetch_clean_html(url)
        if not html_content:
            raise CommandError("Impossible de récupérer ou nettoyer le contenu HTML.")

        # --- ÉTAPE 2 : Extraction structurée avec Ollama ---
        self.stdout.write(f"Extraction des données avec Ollama ({model_name})...")
        extracted_data = self.extract_with_ollama(html_content, model_name)

        if not extracted_data:
            raise CommandError("Échec de l'extraction des données via Ollama.")

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

    def extract_with_ollama(self, html_snippet: str, model_name: str) -> ExtractedProductData | None:
        prompt = (
            "Analyse ce fragment HTML d'une page e-commerce. "
            "Extrais le nom du produit principal, son prix actuel, la devise, son état de stock "
            "et la référence/EAN/SKU si disponible."
        )

        try:
            response = ollama.chat(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Tu es un extracteur de données e-commerce précis."},
                    {"role": "user", "content": f"{prompt}\n\nHTML:\n{html_snippet}"},
                ],
                # Passer directement la classe Pydantic
                format=ExtractedProductData.model_json_schema(), 
                options={"temperature": 0.1},
            )

            raw_json = response["message"]["content"]
            return ExtractedProductData.model_validate_json(raw_json)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Erreur avec Ollama : {e}"))
            return None
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