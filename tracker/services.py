import os
import re
import time
from decimal import Decimal
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, Field

try:
    import boto3
except ImportError:  # pragma: no cover
    boto3 = None

try:
    import ollama
except ImportError:  # pragma: no cover
    ollama = None

from tracker.currency import normalize_currency_code
from tracker.extractors import extract_structured_product
from tracker.models import PriceListing, Product, Retailer
from tracker.product_matching import match_product


class ExtractedProductData(BaseModel):
    product_name: str = Field(description="Nom complet du produit")
    price: float = Field(description="Prix actuel")
    currency: str = Field(description="Code devise")
    in_stock: bool = Field(description="Disponibilité")
    sku_or_ean: str | None = None


def build_fetch_headers() -> dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
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
    host = (parsed.netloc or parsed.path).split(":")[0].lower().removeprefix("www.")
    if not host:
        return "all", ""
    return host, f"{parsed.scheme}://{parsed.netloc or host}"


def ensure_retailer_for_site(site_filter: str | None):
    domain, base_url = normalize_site_filter(site_filter)
    if domain == "all" or not base_url:
        return None
    retailer, _ = Retailer.objects.get_or_create(name=domain.capitalize(), defaults={"base_url": base_url})
    if retailer.base_url != base_url:
        retailer.base_url = base_url
        retailer.save(update_fields=["base_url"])
    return retailer


def get_llm_config() -> dict:
    configured = getattr(settings, "LLM_CONFIG", {}) or {}
    default_model = (configured.get("default_model") or os.environ.get("LLM_MODEL") or "").strip()
    if not default_model:
        raise ImproperlyConfigured("LLM_MODEL must be set in .env.")
    models = configured.get("models") or []
    if not isinstance(models, list):
        models = [str(models)] if models else []
    if default_model not in models:
        models.insert(0, default_model)
    return {
        "provider": (configured.get("provider") or os.environ.get("LLM_PROVIDER") or "bedrock").strip().lower(),
        "default_model": default_model,
        "models": models,
        "region": (configured.get("region") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1").strip(),
        "access_key_id": (configured.get("access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("BEDROCK_ACCESS_KEY_ID") or "").strip(),
        "secret_access_key": (configured.get("secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("BEDROCK_SECRET_ACCESS_KEY") or "").strip(),
        "session_token": (configured.get("session_token") or os.environ.get("AWS_SESSION_TOKEN") or os.environ.get("BEDROCK_SESSION_TOKEN") or "").strip(),
        "bearer_token": (configured.get("bearer_token") or os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip(),
        "base_url": (configured.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "").strip(),
    }


def resolve_bedrock_model_id(model_name: str, region: str | None = None) -> str:
    return (model_name or "").strip()


def fetch_and_clean_html(url: str) -> str | None:
    session = requests.Session()
    session.headers.update(build_fetch_headers())
    for attempt in range(3):
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            if response.status_code in {403, 429, 500, 502, 503, 504}:
                raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(1)

    encoding = response.encoding if isinstance(response.encoding, str) else "utf-8"
    try:
        text = response.content.decode(encoding, errors="replace")
    except (LookupError, TypeError):
        text = response.content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for element in soup(["style", "svg", "noscript", "header", "footer", "nav"]):
        element.decompose()
    return str(soup.find("body") or soup)[:80000]


def _parse_fallback_price(raw: str) -> float:
    value = raw.replace(" ", "").strip()
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        tail = value.rsplit(",", 1)[1]
        value = value.replace(",", ".") if len(tail) <= 2 else value.replace(",", "")
    elif value.count(".") == 1 and len(value.rsplit(".", 1)[1]) > 2:
        value = value.replace(".", "")
    return float(value)


def _fallback_extract_html(html_snippet: str) -> ExtractedProductData | None:
    soup = BeautifulSoup(html_snippet, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    heading = " ".join(node.get_text(" ", strip=True) for node in soup.find_all(["h1", "h2", "h3"])[:3])
    product_name = re.sub(r"\s+", " ", title or heading).strip()
    text = soup.get_text(" ", strip=True)
    patterns = [
        r"(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))\s*(?:€|EUR|USD|CDF|FC)",
        r"(?:€|EUR|USD|CDF|FC)\s*(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))",
    ]
    raw_price = next((m.group(1) for p in patterns if (m := re.search(p, text, flags=re.IGNORECASE))), None)
    if not raw_price:
        return None
    currency = "CDF" if re.search(r"\bCDF\b|\bFC\b", text, re.I) else "USD" if re.search(r"\bUSD\b|\$", text, re.I) else "EUR"
    lowered = text.lower()
    in_stock = not any(token in lowered for token in ["rupture", "épuisé", "epuise", "indisponible", "out of stock", "sold out"])
    return ExtractedProductData(product_name=product_name or "Produit non identifié", price=_parse_fallback_price(raw_price), currency=currency, in_stock=in_stock)


def extract_with_ollama(html_snippet: str, model_name: str) -> ExtractedProductData | None:
    if ollama is None:
        raise RuntimeError("Le paquet ollama n'est pas installé.")
    response = ollama.chat(model=model_name, messages=[
        {"role": "system", "content": "Tu es un extracteur de données e-commerce précis."},
        {"role": "user", "content": f"Extrais nom, prix, devise, stock et SKU/EAN.\n\nHTML:\n{html_snippet}"},
    ], format=ExtractedProductData.model_json_schema(), options={"temperature": 0.1})
    return ExtractedProductData.model_validate_json(response["message"]["content"])


def extract_with_bedrock(html_snippet: str, model_name: str) -> ExtractedProductData | None:
    if boto3 is None:
        raise RuntimeError("boto3 n'est pas installé.")
    config = get_llm_config()
    client_kwargs = {"region_name": config["region"]}
    if config["access_key_id"]:
        client_kwargs["aws_access_key_id"] = config["access_key_id"]
    if config["secret_access_key"]:
        client_kwargs["aws_secret_access_key"] = config["secret_access_key"]
    if config["session_token"]:
        client_kwargs["aws_session_token"] = config["session_token"]
    client = boto3.client("bedrock-runtime", **client_kwargs)
    response = client.converse(modelId=resolve_bedrock_model_id(model_name, config["region"]), messages=[{
        "role": "user", "content": [{"text": f"Extrais nom, prix, devise, stock et SKU/EAN en JSON.\n\nHTML:\n{html_snippet}"}],
    }], inferenceConfig={"temperature": 0.1})
    text = "".join(block.get("text", "") for block in response.get("output", {}).get("message", {}).get("content", []) if isinstance(block, dict))
    return ExtractedProductData.model_validate_json(text) if text else None


def _extract_llm_only(html_snippet: str, model_name: str | None = None) -> ExtractedProductData | None:
    config = get_llm_config()
    selected_model = (model_name or config["default_model"]).strip()
    try:
        if config["provider"] == "bedrock":
            return extract_with_bedrock(html_snippet, selected_model)
        return extract_with_ollama(html_snippet, selected_model)
    except Exception:
        return None


def extract_with_llm(html_snippet: str, model_name: str | None = None) -> ExtractedProductData | None:
    return _extract_llm_only(html_snippet, model_name) or _fallback_extract_html(html_snippet)


def _structured_to_extracted(html: str) -> ExtractedProductData | None:
    structured = extract_structured_product(html)
    if structured is None:
        return None
    return ExtractedProductData(product_name=structured.product_name, price=float(structured.price), currency=structured.currency, in_stock=structured.in_stock, sku_or_ean=structured.sku_or_ean)


def _detect_structured_source(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return "jsonld" if soup.find("script", attrs={"type": "application/ld+json"}) else "meta"


def _confidence_for(source: str, match_score: float, has_sku: bool) -> Decimal:
    base = {"jsonld": 0.92, "meta": 0.84, "llm": 0.76, "html": 0.62, "cache": 0.70}.get(source, 0.55)
    score = base + (0.04 if has_sku else 0.0) + (0.04 * max(0.0, min(match_score, 1.0)))
    return Decimal(str(round(min(score, 0.99), 4)))


def _cached_listing_for_url(url: str, expected_query: str | None = None):
    listing = PriceListing.objects.select_related("product", "retailer").filter(url=url, is_active=True).order_by("-scraped_at").first()
    if listing is None:
        return None
    if expected_query and not match_product(expected_query, listing.product.name).is_match:
        return None
    return listing


def _is_relevant_product_match(product_name: str, query: str | None) -> bool:
    return True if not query else match_product(query, product_name).is_match


def _is_not_found_page(html_content: str | None) -> bool:
    if not html_content:
        return False
    lower = html_content.lower()
    return any(marker in lower for marker in ["404 page introuvable", "page introuvable", "not found", "page not found", "could not find this page", "we couldn't find this page"])


def _has_exploitable_product_structure(html_content: str | None) -> bool:
    if not html_content:
        return False
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(" ", strip=True)
    if len(text) < 40:
        return False
    combined = text.lower()
    price_like = bool(re.search(r"(?:€|eur|usd|cdf|fc|\$)\s*\d|\d[\d\s\.,]*\s*(?:€|eur|usd|cdf|fc|\$)", text, re.I))
    product_signal = any(token in combined for token in ["prix", "price", "en stock", "in stock", "sku", "ean", "product", "produit", "ajouter au panier", "add to cart", "acheter", "buy now"])
    if any(token in combined for token in ["bienvenue", "newsletter", "contact", "blog"]) and not price_like:
        return False
    return product_signal and len(soup.find_all(["h1", "h2", "h3", "p", "div", "span"])) >= 2


def process_url_and_save(url: str, model_name: str | None = None, expected_query: str | None = None, allowed_hosts: list[str] | None = None):
    parsed = urlparse(url)
    if _is_homepage_url(url):
        return None, "URL de page d'accueil non exploitable pour un produit."
    if _is_category_or_listing_url(url):
        return None, "URL de liste ou catégorie non exploitable pour un produit unique."

    cached_listing = _cached_listing_for_url(url, expected_query)
    html = fetch_and_clean_html(url)
    if not html:
        return (cached_listing, None) if cached_listing else (None, "Impossible de récupérer le contenu de la page web.")
    if _is_not_found_page(html):
        return (cached_listing, None) if cached_listing else (None, "Page introuvable ou URL produit inexistante.")

    extracted = _structured_to_extracted(html)
    source = _detect_structured_source(html) if extracted else ""
    if extracted is None and expected_query and not _has_exploitable_product_structure(html):
        return (cached_listing, None) if cached_listing else (None, "Page sans structure de produit exploitable.")
    if extracted is None:
        extracted = _extract_llm_only(html, model_name)
        source = "llm" if extracted else "html"
        if extracted is None:
            extracted = _fallback_extract_html(html)
    if not extracted:
        return (cached_listing, None) if cached_listing else (None, "L'extraction a échoué.")

    product_name = (extracted.product_name or "").strip()
    currency = normalize_currency_code(extracted.currency)
    price = Decimal(str(extracted.price)).quantize(Decimal("0.01"))
    if not product_name or product_name.lower() in {"unknown", "inconnu", "n/a", "na"} or price <= 0:
        return (cached_listing, None) if cached_listing else (None, "Données extraites invalides ou page non exploitable.")

    host = (parsed.netloc or "").lower().removeprefix("www.")
    allowed = {h.lower().removeprefix("www.") for h in (allowed_hosts or [])}
    match = match_product(expected_query, product_name) if expected_query else None
    if match and host not in allowed and not match.is_match:
        return (cached_listing, None) if cached_listing else (None, f"Produit non pertinent ({match.reason}, score={match.score:.2f}).")
    match_score = match.score if match else 1.0

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    with transaction.atomic():
        retailer, _ = Retailer.objects.get_or_create(name=(host or "Site inconnu").capitalize(), defaults={"base_url": base_url})
        if retailer.base_url != base_url:
            retailer.base_url = base_url
            retailer.save(update_fields=["base_url"])

        product = Product.objects.filter(sku_or_ean=extracted.sku_or_ean).first() if extracted.sku_or_ean else None
        if not product and cached_listing:
            product = cached_listing.product
        if not product:
            product = Product.objects.filter(name__iexact=product_name).first()
        if not product:
            product = Product.objects.create(name=product_name, sku_or_ean=extracted.sku_or_ean)

        listing = PriceListing.objects.filter(product=product, retailer=retailer, url=url).first() or cached_listing or PriceListing(product=product, retailer=retailer, url=url)
        listing.product = product
        listing.retailer = retailer
        listing.price = price
        listing.currency = currency
        listing.in_stock = extracted.in_stock
        listing.is_active = True
        listing.extraction_source = source or "unknown"
        listing.match_score = Decimal(str(round(match_score, 4)))
        listing.confidence_score = _confidence_for(source, match_score, bool(extracted.sku_or_ean))
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
    if path in {"fr", "en", "es", "de", "it", "pt", "ar", "ru", "zh", "tr", "sw"}:
        return True
    parts = [p for p in path.split("/") if p]
    return len(parts) == 1 and parts[0] not in {"products", "product", "produits", "produit"}


def _is_category_or_listing_url(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    if ".oembed" in path or path.endswith("/oembed"):
        return True
    collection_tokens = ("/categorie/", "/category/", "/categories/", "/collections/", "/collection/", "/shop/", "/search/", "/ads/", "/annonces/", "/market/", "/en/ads/")
    if any(token in path for token in collection_tokens):
        return True
    return False


def _is_comparator_url(url: str) -> bool:
    combined = f"{urlparse(url).netloc} {urlparse(url).path}".lower()
    return any(token in combined for token in ["comparateur", "comparaison", "compare", "comparison", "meilleur-prix", "best-price", "price-comparison", "pricecomparison"])


def _is_low_quality_source_url(url: str) -> bool:
    parsed = urlparse(url)
    host, path = parsed.netloc.lower().removeprefix("www."), parsed.path.lower()
    social_hosts = ("tiktok.com", "instagram.com", "facebook.com", "fb.com", "x.com", "twitter.com", "pinterest.com")
    social_paths = ("/shop/", "/products/", "/product/", "/items/", "/item/", "/marketplace/", "/p/", "/video/")
    if any(host.endswith(h) for h in social_hosts) and any(token in path for token in social_paths):
        return False
    return any(token in f"{host} {path}" for token in ["forum", "blog", "discussion", "topic", "quora", "reddit", "youtube", "wikipedia", "linkedin", "discord", "telegram", "whatsapp"])


def _collect_search_urls(search_term: str, max_results: int) -> list[str]:
    urls = []
    with DDGS() as ddgs:
        for result in ddgs.text(search_term, max_results=max_results):
            url = str(result.get("href") or "").strip()
            if url and not (_is_homepage_url(url) or _is_category_or_listing_url(url) or _is_comparator_url(url) or _is_low_quality_source_url(url)) and url not in urls:
                urls.append(url)
    return urls


def cleanup_stale_listings(days: int = 30, product_id: int | None = None) -> int:
    cutoff = timezone.now() - timezone.timedelta(days=days)
    queryset = PriceListing.objects.filter(scraped_at__lt=cutoff)
    if product_id is not None:
        queryset = queryset.filter(product_id=product_id)
    listing_count = queryset.count()
    queryset.delete()
    return listing_count


def _get_sort_rank(item):
    normalized = getattr(item, "normalized_price", None)
    price = normalized if normalized is not None else getattr(item, "price", 0)
    return (0 if getattr(item, "in_stock", True) else 1, float(price))


def _deduplicate_results(results):
    deduped = {}
    for item in results:
        if item is None:
            continue
        url = getattr(item, "url", "")
        key = (getattr(item, "product_id", None), getattr(item, "retailer_id", None), url) if url else (id(item),)
        if key not in deduped or _get_sort_rank(item) < _get_sort_rank(deduped[key]):
            deduped[key] = item
    return list(deduped.values())


def search_and_scrape_product(product_query: str, site_filter: str = "all", model_name: str | None = None, max_results: int = 3):
    cleanup_stale_listings(days=getattr(settings, "LISTING_STALE_DAYS", 30))
    selected_model = (model_name or get_llm_config()["default_model"]).strip()
    results, errors = [], []
    site_filter = (site_filter or "all").strip() or "all"
    country = getattr(settings, "DEFAULT_SEARCH_COUNTRY", "RDC")
    local_domains = getattr(settings, "LOCAL_SEARCH_DOMAINS", ["drcmart.com", "mobile-rdc.com"]) or []
    if isinstance(local_domains, str):
        local_domains = [p.strip() for p in local_domains.split(",") if p.strip()]
    site_filters = [] if site_filter == "all" else [p.strip() for p in site_filter.split(",") if p.strip()]
    for site in site_filters:
        ensure_retailer_for_site(site)
    search_terms = []
    if site_filters:
        for site in site_filters:
            domain, _ = normalize_site_filter(site)
            search_terms.append(f"site:{domain} {product_query}")
    else:
        search_terms.extend(f"site:{domain} {product_query} {country} prix" for domain in local_domains)
        search_terms.extend([f"{product_query} {country} acheter prix", f"{product_query} acheter prix", f"{product_query} prix"])
    urls = []
    for term in search_terms:
        try:
            found = _collect_search_urls(term, max_results)
        except Exception as exc:
            return [], [f"Erreur lors de la recherche : {exc}"]
        for url in found:
            if url not in urls:
                urls.append(url)
        if not site_filters and urls:
            break
    if not urls:
        return [], ["Aucune page exploitable n'a été trouvée pour ce produit."]
    allowed_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    for url in urls:
        listing, error = process_url_and_save(url, model_name=selected_model, expected_query=product_query, allowed_hosts=allowed_hosts)
        if listing:
            results.append(listing)
        elif error:
            errors.append(f"{url}: {error}")
    results = _deduplicate_results(results)
    results.sort(key=_get_sort_rank)
    return (results, []) if results else ([], errors or ["Aucune page exploitable n'a été trouvée pour ce produit."])
