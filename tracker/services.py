import json
import os
import re
import time
from decimal import Decimal
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from ddgs import DDGS
from django.conf import settings


try:
    import boto3
except ImportError:  # pragma: no cover - optional dependency
    boto3 = None

try:
    import ollama
except ImportError:  # pragma: no cover - optional dependency
    ollama = None

from django.db import transaction
from django.utils import timezone
from tracker.models import Product, Retailer, PriceListing


def build_fetch_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def normalize_site_filter(site_filter: str | None) -> tuple[str, str]:
    if site_filter is None:
        return "all", ""

    site = site_filter.strip()
    if not site or site.lower() in {"all", "tous", "tous les sites"}:
        return "all", ""

    if "://" not in site:
        site = f"https://{site}"

    parsed = urlparse(site)
    host = parsed.netloc or parsed.path
    if not host:
        return "all", ""

    host = host.split(":")[0].lower()
    host = host.removeprefix("www.")
    base_url = f"{parsed.scheme}://{parsed.netloc or host}"
    return host, base_url


def ensure_retailer_for_site(site_filter: str | None):
    domain, base_url = normalize_site_filter(site_filter)
    if domain == "all" or not base_url:
        return None

    retailer, _ = Retailer.objects.get_or_create(
        name=domain.capitalize(),
        defaults={"base_url": base_url},
    )
    if retailer.base_url != base_url:
        retailer.base_url = base_url
        retailer.save(update_fields=["base_url"])
    return retailer


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


def fetch_and_clean_html(url: str) -> str | None:
    session = requests.Session()
    session.headers.update(build_fetch_headers())

    final_response = None
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            final_response = response
            content = response.content
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1)
            continue
    else:
        return None

    encoding = final_response.encoding if isinstance(final_response.encoding, str) else "utf-8"
    encoding = encoding.lower()
    try:
        text = content.decode(encoding, errors="replace")
    except (LookupError, TypeError):
        text = content.decode("utf-8", errors="replace")

    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception:
        return None

    for element in soup(["script", "style", "svg", "noscript", "header", "footer", "nav"]):
        element.decompose()

    target = soup.find("body") or soup
    return str(target)[:80000]


def _fallback_extract_html(html_snippet: str) -> ExtractedProductData | None:
    soup = BeautifulSoup(html_snippet, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    heading = " ".join(part.get_text(" ", strip=True) for part in soup.find_all(["h1", "h2", "h3"])[:3])
    product_name = title or heading or (soup.find("meta", property="og:title") or {}).get("content", "")
    product_name = re.sub(r"\s+", " ", product_name).strip()

    text_nodes = soup.get_text(" ", strip=True)
    price_match = None
    for pattern in [
        r"(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))\s*(?:€|EUR|usd|cdf|fc|frw)",
        r"(?:€|EUR|USD|CDF|FC|FRW)\s*(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))",
        r"(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))",
    ]:
        match = re.search(pattern, text_nodes, flags=re.IGNORECASE)
        if match:
            price_match = match.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            break

    if not price_match:
        return None

    price = float(price_match)
    currency = "EUR"
    if re.search(r"\bUSD\b|\$\b", text_nodes, flags=re.IGNORECASE):
        currency = "USD"
    elif re.search(r"\bCDF\b|\bFC\b", text_nodes, flags=re.IGNORECASE):
        currency = "CDF"
    elif re.search(r"\bEUR\b|€", text_nodes, flags=re.IGNORECASE):
        currency = "EUR"

    stock_text = text_nodes.lower()
    in_stock = not any(token in stock_text for token in ["rupture", "épuisé", "epuise", "indisponible", "out of stock", "sold out"])

    return ExtractedProductData(
        product_name=product_name or "Produit non identifié",
        price=price,
        currency=currency,
        in_stock=in_stock,
        sku_or_ean=None,
    )


def get_llm_config() -> dict:
    configured = getattr(settings, "LLM_CONFIG", {}) or {}
    provider = (configured.get("provider") or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()

    env_models = [part.strip() for part in os.environ.get("LLM_MODELS", "").split(",") if part.strip()]
    configured_models = configured.get("models") or []
    if not isinstance(configured_models, list):
        configured_models = [str(configured_models)] if configured_models else []

    models = configured_models or env_models
    default_model = (configured.get("default_model") or (models[0] if models else os.environ.get("LLM_MODEL")) or "google.gemma-3-12b-it").strip()

    if env_models and models and (models[0] != env_models[0]):
        models = env_models + [m for m in models if m not in env_models]
    if default_model and default_model not in models:
        models.insert(0, default_model)
    if not models:
        models = [default_model]

    return {
        "provider": provider,
        "default_model": default_model or models[0],
        "models": models,
        "region": (configured.get("region") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1").strip(),
        "access_key_id": (configured.get("access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("BEDROCK_ACCESS_KEY_ID") or "").strip(),
        "secret_access_key": (configured.get("secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("BEDROCK_SECRET_ACCESS_KEY") or "").strip(),
        "session_token": (configured.get("session_token") or os.environ.get("AWS_SESSION_TOKEN") or os.environ.get("BEDROCK_SESSION_TOKEN") or "").strip(),
        "bearer_token": (configured.get("bearer_token") or os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip(),
        "base_url": (configured.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "").strip(),
    }


def resolve_bedrock_model_id(model_name: str, region: str | None = None) -> str:
    name = (model_name or "").strip()
    if not name:
        return name

    lowered = name.lower()
    if lowered.startswith("google.gemma-3-12b-it"):
        return name
    if lowered.startswith("google.gemma-3-4b-it"):
        return name
    return name


def extract_with_ollama(html_snippet: str, model_name: str) -> ExtractedProductData | None:
    if ollama is None:
        raise RuntimeError("Le paquet ollama n'est pas installé.")

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
            format=ExtractedProductData.model_json_schema(),
            options={"temperature": 0.1},
        )
        return ExtractedProductData.model_validate_json(response["message"]["content"])
    except Exception:
        return _fallback_extract_html(html_snippet)


def extract_with_bedrock(html_snippet: str, model_name: str) -> ExtractedProductData | None:
    if boto3 is None:
        if ollama is not None:
            return extract_with_ollama(html_snippet, model_name)
        return _fallback_extract_html(html_snippet)

    config = get_llm_config()
    client_kwargs = {
        "region_name": config.get("region"),
    }
    if config.get("access_key_id"):
        client_kwargs["aws_access_key_id"] = config["access_key_id"]
    if config.get("secret_access_key"):
        client_kwargs["aws_secret_access_key"] = config["secret_access_key"]
    if config.get("session_token"):
        client_kwargs["aws_session_token"] = config["session_token"]

    prompt = (
        "Analyse ce fragment HTML d'une page e-commerce. "
        "Extrais le nom du produit principal, son prix actuel, la devise, son état de stock "
        "et la référence/EAN/SKU si disponible."
    )
    try:
        client = boto3.client("bedrock-runtime", **client_kwargs)
        model_id = resolve_bedrock_model_id(model_name, config.get("region"))
        response = client.converse(
            modelId=model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": f"{prompt}\n\nHTML:\n{html_snippet}"}],
                }
            ],
            inferenceConfig={"temperature": 0.1},
        )
        content_blocks = response.get("output", {}).get("message", {}).get("content", [])
        text_parts = []
        for block in content_blocks:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    text_parts.append(text)
        if not text_parts:
            return None
        raw_json = "".join(text_parts)
        return ExtractedProductData.model_validate_json(raw_json)
    except Exception:
        try:
            return extract_with_ollama(html_snippet, model_name)
        except Exception:
            pass
        return _fallback_extract_html(html_snippet)


def extract_with_llm(html_snippet: str, model_name: str | None = None) -> ExtractedProductData | None:
    config = get_llm_config()
    selected_model = (model_name or config.get("default_model") or config["models"][0]).strip()
    provider = config.get("provider", "ollama")

    if provider == "bedrock":
        try:
            result = extract_with_bedrock(html_snippet, selected_model)
            if result is not None:
                return result
        except Exception:
            pass
        try:
            return extract_with_ollama(html_snippet, selected_model)
        except Exception:
            pass
        return _fallback_extract_html(html_snippet)

    try:
        return extract_with_ollama(html_snippet, selected_model)
    except Exception:
        return _fallback_extract_html(html_snippet)


def _is_relevant_product_match(product_name: str, query: str | None) -> bool:
    if not query:
        return True

    normalized_query = re.sub(r"\W+", " ", query.lower()).strip()
    normalized_name = re.sub(r"\W+", " ", product_name.lower()).strip()
    if not normalized_query or not normalized_name:
        return True
    if normalized_query in normalized_name:
        return True

    query_tokens = set(normalized_query.split())
    name_tokens = set(normalized_name.split())
    if not query_tokens or not name_tokens:
        return True
    overlap = query_tokens & name_tokens
    return bool(overlap) and (len(overlap) / len(query_tokens) >= 0.4)


def _is_not_found_page(html_content: str | None) -> bool:
    if not html_content:
        return False
    lower = html_content.lower()
    not_found_markers = (
        "404 page introuvable",
        "page introuvable",
        "not found",
        "page not found",
        "could not find this page",
        "we couldn't find this page",
        "we could not find this page",
    )
    return any(marker in lower for marker in not_found_markers)


def _has_exploitable_product_structure(html_content: str | None) -> bool:
    if not html_content:
        return False
    soup = BeautifulSoup(html_content, "html.parser")
    if not soup:
        return False

    text = soup.get_text(" ", strip=True)
    if len(text) < 40:
        return False

    title = (soup.title.get_text(" ", strip=True) if soup.title else "")
    headings = " ".join(node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2", "h3"])[:10])
    combined = f"{title} {headings} {text}".lower()

    price_like = bool(
        re.search(
            r"(?:€|eur|usd|cdf|fc|frw|£|\$)\s*\d|\d{1,3}(?:[\s\.\,]\d{3})*(?:[\.,]\d{1,2})\s*(?:€|eur|usd|cdf|fc|frw|£|\$)",
            html_content,
            flags=re.IGNORECASE,
        )
    )

    strong_cta = bool(
        re.search(r"(?:add to cart|ajouter au panier|acheter maintenant|buy now|in stock|en stock|sku|ean|référence|reference)", combined, flags=re.IGNORECASE)
    )

    generic_markers = (
        "accueil",
        "bienvenue",
        "actualit",
        "blog",
        "blogue",
        "news",
        "contact",
        "a propos",
        "apropos",
        "categorie",
        "collection",
        "featured",
        "nouveaut",
        "promotions",
        "newsletter",
    )
    if any(marker in combined for marker in generic_markers):
        if not (price_like or strong_cta):
            return False

    product_indicators = (
        "prix",
        "price",
        "add to cart",
        "ajouter au panier",
        "en stock",
        "in stock",
        "sku",
        "ean",
        "code produit",
        "reference",
        "référence",
        "product",
        "produit",
        "buy now",
        "acheter maintenant",
    )
    if not any(token in combined for token in product_indicators):
        return False

    candidate_nodes = soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "span", "div"])
    structural_signal = sum(1 for node in candidate_nodes if node.get_text(" ", strip=True))
    return structural_signal >= 3


def process_url_and_save(
    url: str,
    model_name: str | None = None,
    expected_query: str | None = None,
    allowed_hosts: list[str] | None = None,
):
    parsed_url = urlparse(url)
    if _is_homepage_url(url):
        return None, "URL de page d'accueil non exploitable pour un produit."
    if _is_category_or_listing_url(url):
        return None, "URL de liste ou catégorie non exploitable pour un produit unique."

    html_content = fetch_and_clean_html(url)
    if not html_content:
        return None, "Impossible de récupérer le contenu de la page web."
    if _is_not_found_page(html_content):
        return None, "Page introuvable ou URL produit inexistante."
    if not _has_exploitable_product_structure(html_content):
        return None, "Page sans structure de produit exploitable; capture interrompue avant l'appel au modèle."

    config = get_llm_config()
    selected_model = (model_name or config.get("default_model") or config["models"][0]).strip()
    extracted_data = extract_with_llm(html_content, selected_model)
    if not extracted_data:
        return None, f"L'extraction avec {config.get('provider', 'llm').upper()} a échoué."

    product_name = (extracted_data.product_name or "").strip()
    currency = (extracted_data.currency or "").strip()
    price = Decimal(str(float(extracted_data.price))).quantize(Decimal("0.01"))

    invalid_name = product_name.lower() in {"unknown", "inconnu", "n/a", "na", "non identifié", "non identifie"}
    invalid_currency = currency.lower() in {"unknown", "inconnu", "n/a", "na", ""}
    unrealistic_price = not (0 < price <= 20000)

    if invalid_name or invalid_currency or unrealistic_price:
        return None, "Données extraites invalides ou page non exploitable."

    product_name = product_name or "Produit non identifié"
    currency = currency or "EUR"

    host = (parsed_url.netloc or "").lower().replace("www.", "")
    allowed = set((host_name.lower().replace("www.", "") for host_name in (allowed_hosts or [])))
    if expected_query and host not in allowed and not _is_relevant_product_match(product_name, expected_query):
        return None, "Produit non pertinent pour la recherche demandée."

    domain = parsed_url.netloc.replace("www.", "")
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    with transaction.atomic():
        retailer, _ = Retailer.objects.get_or_create(
            name=(domain or "Site inconnu").capitalize(),
            defaults={"base_url": base_url},
        )
        if retailer.base_url != base_url:
            retailer.base_url = base_url
            retailer.save(update_fields=["base_url"])

        product = None
        if extracted_data.sku_or_ean:
            product = Product.objects.filter(sku_or_ean=extracted_data.sku_or_ean).first()

        if not product:
            product, _ = Product.objects.get_or_create(
                name=product_name,
                defaults={"sku_or_ean": extracted_data.sku_or_ean},
            )

        listing = PriceListing.objects.filter(
            product=product,
            retailer=retailer,
            url=url,
        ).first()
        if listing is None:
            listing = PriceListing(
                product=product,
                retailer=retailer,
                url=url,
            )

        listing.price = price
        listing.currency = currency
        listing.in_stock = extracted_data.in_stock
        listing.save()

    return listing, None


def _is_homepage_url(url: str) -> bool:
    if not url:
        return True

    parsed = urlparse(url)
    if not parsed.netloc:
        return True

    path = (parsed.path or "").strip("/").lower()
    if not path:
        return True

    locale_roots = {"fr", "en", "es", "de", "it", "pt", "ar", "ru", "zh", "tr", "sw"}
    if path in locale_roots:
        return True

    parts = [part for part in path.split("/") if part]
    if len(parts) == 1 and parts[0] in locale_roots:
        return True

    if len(parts) == 1 and parts[0] not in {"products", "product", "produits", "produit"}:
        return True

    return False


def _is_category_or_listing_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    path = (parsed.path or "").lower()
    if ".oembed" in path or path.endswith("/oembed"):
        return True

    collection_tokens = (
        "/categorie/",
        "/category/",
        "/categories/",
        "/collections/",
        "/collection/",
        "/shop/",
        "/search/",
        "/ads/",
        "/annonces/",
        "/market/",
        "/en/ads/",
    )
    product_tokens = (
        "/produits/",
        "/produit/",
        "/products/",
        "/product/",
    )

    if any(token in path for token in collection_tokens):
        return True

    if any(token in path for token in product_tokens):
        return False

    path_parts = [part for part in path.strip("/").split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] in {"fr", "en", "es", "de", "it", "pt", "ar", "ru", "zh", "tr", "sw"}:
        if "collections" in path_parts or "categorie" in path_parts or "category" in path_parts:
            return True

    return False


def _is_comparator_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = (parsed.path or "").lower()
    combined = f"{host} {path}"
    patterns = (
        "comparateur",
        "comparaison",
        "compare",
        "comparison",
        "meilleur-prix",
        "meilleurprix",
        "best-price",
        "price-comparison",
        "pricecomparison",
        "deal",
        "promos",
        "promo",
        "offers",
        "offres",
    )
    return any(token in combined for token in patterns)


def _is_low_quality_source_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = (parsed.path or "").lower()
    combined = f"{host} {path}"

    commerce_social_hosts = (
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "fb.com",
        "x.com",
        "twitter.com",
        "pinterest.com",
        "snapchat.com",
    )
    commerce_social_paths = (
        "/shop/",
        "/products/",
        "/product/",
        "/items/",
        "/item/",
        "/marketplace/",
        "/commerce/",
        "/p/",
        "/video/",
    )
    if any(host.endswith(social_host) for social_host in commerce_social_hosts):
        if any(token in path for token in commerce_social_paths) or "/p/" in path or "/video/" in path:
            return False

    patterns = (
        "forum",
        "forums",
        "blog",
        "blogs",
        "discussion",
        "topic",
        "avis",
        "commentaire",
        "review",
        "reviews",
        "quora",
        "reddit",
        "youtube",
        "wikipedia",
        "linkedin",
        "discord",
        "telegram",
        "whatsapp",
    )
    return any(token in combined for token in patterns)


def _collect_search_urls(search_term: str, max_results: int) -> list[str]:
    urls: list[str] = []
    with DDGS() as ddgs:
        search_results = ddgs.text(search_term, max_results=max_results)
        for res in search_results:
            url = str(res.get("href") or "").strip()
            if not url:
                continue
            if _is_homepage_url(url) or _is_category_or_listing_url(url):
                continue
            if _is_comparator_url(url) or _is_low_quality_source_url(url):
                continue
            if url not in urls:
                urls.append(url)
    return urls


def cleanup_stale_listings(days: int = 30, product_id: int | None = None) -> int:
    cutoff = timezone.now() - timezone.timedelta(days=days)
    queryset = PriceListing.objects.filter(scraped_at__lt=cutoff)
    if product_id is not None:
        queryset = queryset.filter(product_id=product_id)
    return queryset.delete()[0]


def _get_sort_rank(item):
    in_stock = getattr(item, "in_stock", True)
    price = getattr(item, "price", 0)
    return (0 if in_stock else 1, float(price))


def _deduplicate_results(results):
    deduped = {}
    for item in results:
        if item is None:
            continue

        url = getattr(item, "url", "")
        product_id = getattr(item, "product_id", None)
        retailer_id = getattr(item, "retailer_id", None)
        if url:
            key = (product_id, retailer_id, url)
        else:
            key = (id(item),)

        if key not in deduped:
            deduped[key] = item
            continue

        current = deduped[key]
        if _get_sort_rank(item) < _get_sort_rank(current):
            deduped[key] = item
    return list(deduped.values())


def search_and_scrape_product(
    product_query: str,
    site_filter: str = "all",
    model_name: str | None = None,
    max_results: int = 3,
):
    stale_days = getattr(settings, "LISTING_STALE_DAYS", 30)
    cleanup_stale_listings(days=stale_days)

    results = []
    errors = []
    selected_model = (model_name or get_llm_config().get("default_model") or "google.gemma-3-12b-it").strip()

    site_filter = site_filter.strip() if isinstance(site_filter, str) else ""
    if not site_filter:
        site_filter = "all"

    default_country = getattr(settings, "DEFAULT_SEARCH_COUNTRY", "RDC")
    local_domains = getattr(settings, "LOCAL_SEARCH_DOMAINS", ["drcmart.com", "mobile-rdc.com"]) or []
    if isinstance(local_domains, str):
        local_domains = [part.strip() for part in local_domains.split(",") if part.strip()]
    local_domains = [domain.lower().removeprefix("www.") for domain in local_domains if domain.strip()]

    site_filters = []
    if site_filter != "all":
        site_filters = [part.strip() for part in site_filter.split(",") if part.strip()]
        for site in site_filters:
            ensure_retailer_for_site(site)

    search_terms = []
    if site_filters:
        for site in site_filters:
            normalized_site, _ = normalize_site_filter(site)
            if normalized_site != "all":
                search_terms.append(f"site:{normalized_site} {product_query}")
    else:
        for domain in local_domains:
            search_terms.append(f"site:{domain} {product_query} {default_country} prix")
        search_terms.extend(
            [
                f"{product_query} {default_country} acheter prix",
                f"{product_query} acheter prix",
                f"{product_query} prix",
            ]
        )

    urls = []
    for search_term in search_terms:
        try:
            candidate_urls = _collect_search_urls(search_term, max_results=max_results)
        except Exception as e:
            return [], [f"Erreur lors de la recherche : {e}"]
        for url in candidate_urls:
            if url not in urls:
                urls.append(url)
        if not site_filters and urls:
            break

    if not urls and not site_filters:
        fallback_terms = [
            f"{product_query} acheter prix",
            f"{product_query} prix",
            f"{product_query}",
        ]
        for search_term in fallback_terms:
            try:
                candidate_urls = _collect_search_urls(search_term, max_results=max_results)
            except Exception as e:
                return [], [f"Erreur lors de la recherche : {e}"]
            for url in candidate_urls:
                if url not in urls:
                    urls.append(url)
            if urls:
                break

    if not urls:
        errors.append("Aucune page exploitable n'a été trouvée pour ce produit.")
        return [], errors

    allowed_hosts = []
    if site_filters:
        allowed_hosts = [normalize_site_filter(site)[0] for site in site_filters]

    for url in urls:
        listing, error = process_url_and_save(
            url,
            model_name=selected_model,
            expected_query=product_query,
            allowed_hosts=allowed_hosts,
        )
        if listing:
            results.append(listing)
        elif error:
            errors.append(f"{url}: {error}")

    if not results and site_filters:
        errors = [error for error in errors if error]
        if not errors:
            errors.append("Aucune page exploitable n'a été trouvée pour ce produit.")
        return results, errors

    results = _deduplicate_results(results)
    results.sort(key=_get_sort_rank)
    if not results:
        errors = [error for error in errors if error]
        if not errors:
            errors.append("Aucune page exploitable n'a été trouvée pour ce produit.")
    return results, errors