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
except ImportError:
    boto3 = None
try:
    import ollama
except ImportError:
    ollama = None

from django.db import transaction
from django.utils import timezone
from tracker.currency import normalize_currency
from tracker.extraction import extract_jsonld_product
from tracker.models import Product, Retailer, PriceListing
from tracker.product_matching import product_match_score


def build_fetch_headers():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7"}


def normalize_site_filter(site_filter):
    if site_filter is None: return "all", ""
    site = site_filter.strip()
    if not site or site.lower() in {"all", "tous", "tous les sites"}: return "all", ""
    if "://" not in site: site = f"https://{site}"
    parsed = urlparse(site)
    host = (parsed.netloc or parsed.path).split(":")[0].lower().removeprefix("www.")
    return (host, f"{parsed.scheme}://{parsed.netloc or host}") if host else ("all", "")


def ensure_retailer_for_site(site_filter):
    domain, base_url = normalize_site_filter(site_filter)
    if domain == "all" or not base_url: return None
    retailer, _ = Retailer.objects.get_or_create(name=domain.capitalize(), defaults={"base_url": base_url})
    if retailer.base_url != base_url:
        retailer.base_url = base_url
        retailer.save(update_fields=["base_url"])
    return retailer


class ExtractedProductData(BaseModel):
    product_name: str
    price: float
    currency: str
    in_stock: bool
    sku_or_ean: str | None = None
    brand: str = ""
    image_url: str = ""
    source: str = "llm"
    confidence: float = Field(default=0.75, ge=0, le=1)


def fetch_and_clean_html(url):
    session = requests.Session()
    session.headers.update(build_fetch_headers())
    for attempt in range(3):
        try:
            response = session.get(url, timeout=20, allow_redirects=True)
            if response.status_code in {403, 429, 500, 502, 503, 504}: raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status()
            text = response.text
            break
        except requests.RequestException:
            if attempt == 2: return None
            time.sleep(1)
    try: soup = BeautifulSoup(text, "html.parser")
    except Exception: return None
    for element in soup(["style", "svg", "noscript", "header", "footer", "nav"]): element.decompose()
    for script in soup.find_all("script"):
        if (script.get("type") or "").lower() != "application/ld+json": script.decompose()
    # Return the document, not only body: schema.org and OpenGraph usually live in head.
    return str(soup)[:80000]


def _fallback_extract_html(html_snippet):
    soup = BeautifulSoup(html_snippet, "html.parser")
    title = (soup.find("meta", property="og:title") or {}).get("content", "")
    heading = soup.find("h1")
    product_name = title or (heading.get_text(" ", strip=True) if heading else "")
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(?:USD|CDF|EUR|FC|€|\$)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(USD|CDF|EUR|FC|€|\$)", text, re.I)
    if not match: return None
    raw = (match.group(1) or match.group(2) or "").strip().replace(" ", "")
    if raw.count(",") == 1 and raw.count(".") == 0: raw = raw.replace(",", ".")
    elif raw.count(".") > 1: raw = raw.replace(".", "")
    try: price = float(raw)
    except ValueError: return None
    marker = (match.group(3) or match.group(0)).upper()
    currency = "CDF" if "CDF" in marker or "FC" in marker else "EUR" if "EUR" in marker or "€" in marker else "USD"
    unavailable = ("rupture", "epuise", "épuisé", "out of stock", "sold out")
    return ExtractedProductData(product_name=product_name, price=price, currency=currency, in_stock=not any(x in text.lower() for x in unavailable), source="html", confidence=0.55)


def get_llm_config():
    configured = getattr(settings, "LLM_CONFIG", {}) or {}
    provider = (configured.get("provider") or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()
    models = configured.get("models") or [configured.get("default_model") or os.environ.get("LLM_MODEL") or "google.gemma-3-12b-it"]
    if not isinstance(models, list): models = [str(models)]
    default_model = (configured.get("default_model") or models[0]).strip()
    return {"provider": provider, "default_model": default_model, "models": models, "region": (configured.get("region") or os.environ.get("AWS_REGION") or "us-east-1").strip(), "access_key_id": (configured.get("access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID") or "").strip(), "secret_access_key": (configured.get("secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip(), "session_token": (configured.get("session_token") or os.environ.get("AWS_SESSION_TOKEN") or "").strip()}


def resolve_bedrock_model_id(model_name, region=None): return (model_name or "").strip()


def extract_with_ollama(html_snippet, model_name):
    if ollama is None: raise RuntimeError("Le paquet ollama n'est pas installé.")
    prompt = "Extrais le produit principal uniquement. Ignore accessoires, livraison, ancien prix et mensualités. Retourne nom, prix actuel, devise, stock, SKU/EAN, marque et image si disponibles."
    response = ollama.chat(model=model_name, messages=[{"role":"system","content":"Tu es un extracteur e-commerce précis."},{"role":"user","content":f"{prompt}\nHTML:\n{html_snippet}"}], format=ExtractedProductData.model_json_schema(), options={"temperature":0.1})
    return ExtractedProductData.model_validate_json(response["message"]["content"])


def extract_with_bedrock(html_snippet, model_name):
    if boto3 is None: raise RuntimeError("boto3 indisponible")
    config = get_llm_config(); kwargs = {"region_name": config["region"]}
    for src, dst in (("access_key_id","aws_access_key_id"),("secret_access_key","aws_secret_access_key"),("session_token","aws_session_token")):
        if config.get(src): kwargs[dst] = config[src]
    client = boto3.client("bedrock-runtime", **kwargs)
    response = client.converse(modelId=resolve_bedrock_model_id(model_name), messages=[{"role":"user","content":[{"text":f"Extrais uniquement le produit principal et retourne du JSON conforme: nom, prix actuel, devise, stock, SKU/EAN, marque.\nHTML:\n{html_snippet}"}]}], inferenceConfig={"temperature":0.1})
    raw = "".join(block.get("text","") for block in response.get("output",{}).get("message",{}).get("content",[]) if isinstance(block,dict))
    return ExtractedProductData.model_validate_json(raw)


def extract_product_data(html_snippet, model_name=None):
    structured = extract_jsonld_product(html_snippet)
    if structured: return ExtractedProductData(**structured)
    config = get_llm_config(); selected = (model_name or config["default_model"]).strip()
    try:
        return extract_with_bedrock(html_snippet, selected) if config["provider"] == "bedrock" else extract_with_ollama(html_snippet, selected)
    except Exception:
        try: return extract_with_ollama(html_snippet, selected)
        except Exception: return _fallback_extract_html(html_snippet)


def extract_with_llm(html_snippet, model_name=None): return extract_product_data(html_snippet, model_name)
def _is_relevant_product_match(product_name, query): return product_match_score(product_name, query).is_match

def _is_not_found_page(html_content):
    lower = (html_content or "").lower()
    return any(marker in lower for marker in ("404 page introuvable","page introuvable","page not found","we couldn't find this page"))

def _has_exploitable_product_structure(html_content):
    if not html_content: return False
    if extract_jsonld_product(html_content): return True
    soup = BeautifulSoup(html_content,"html.parser"); text = soup.get_text(" ",strip=True).lower()
    if len(text) < 40: return False
    has_price = bool(re.search(r"(?:€|eur|usd|cdf|fc|\$)\s*\d|\d[\d\s.,]*\s*(?:€|eur|usd|cdf|fc|\$)",text,re.I))
    return has_price and bool(soup.find("h1")) and any(token in text for token in ("prix","price","stock","panier","cart","sku","product","produit"))


def _find_existing_product(data, expected_query=None):
    if data.sku_or_ean:
        found = Product.objects.filter(sku_or_ean__iexact=data.sku_or_ean).first()
        if found: return found
    first_token = (data.brand or data.product_name).split()[0]
    candidates = Product.objects.filter(name__icontains=first_token)[:50]
    best, best_score = None, 0
    for candidate in candidates:
        score = product_match_score(candidate.name, data.product_name).score
        if score > best_score: best, best_score = candidate, score
    return best if best_score >= 0.88 else None


def process_url_and_save(url, model_name=None, expected_query=None, allowed_hosts=None):
    parsed = urlparse(url)
    if _is_homepage_url(url): return None, "URL de page d'accueil non exploitable pour un produit."
    if _is_category_or_listing_url(url): return None, "URL de liste ou catégorie non exploitable pour un produit unique."
    html = fetch_and_clean_html(url)
    if not html: return None, "Impossible de récupérer le contenu de la page web."
    if _is_not_found_page(html): return None, "Page introuvable ou URL produit inexistante."
    if not _has_exploitable_product_structure(html): return None, "Page sans structure de produit exploitable."
    data = extract_product_data(html, model_name)
    if not data: return None, "Extraction du produit impossible."
    currency = normalize_currency(data.currency); price = Decimal(str(data.price)).quantize(Decimal("0.01"))
    if not data.product_name.strip() or currency is None or not (0 < price <= Decimal("1000000000")): return None, "Données extraites invalides."
    match = product_match_score(data.product_name, expected_query)
    host = (parsed.netloc or "").lower().removeprefix("www."); allowed = {h.lower().removeprefix("www.") for h in (allowed_hosts or [])}
    # Site filtering controls discovery only; relevance is always enforced.
    if expected_query and not match.is_match: return None, f"Produit non pertinent ({match.reason}, score={match.score:.2f})."
    domain = parsed.netloc.removeprefix("www."); base_url = f"{parsed.scheme}://{parsed.netloc}"
    with transaction.atomic():
        retailer, _ = Retailer.objects.get_or_create(name=(domain or "Site inconnu").capitalize(), defaults={"base_url":base_url})
        if retailer.base_url != base_url:
            retailer.base_url = base_url; retailer.save(update_fields=["base_url"])
        product = _find_existing_product(data, expected_query)
        if not product: product = Product.objects.create(name=data.product_name.strip(), sku_or_ean=data.sku_or_ean, brand=data.brand, image_url=data.image_url)
        else:
            changed=[]
            if data.brand and not product.brand: product.brand=data.brand; changed.append("brand")
            if data.image_url and not product.image_url: product.image_url=data.image_url; changed.append("image_url")
            if changed: product.save(update_fields=changed+["updated_at"])
        listing = PriceListing.objects.filter(product=product,retailer=retailer,url=url).first() or PriceListing(product=product,retailer=retailer,url=url)
        listing.price, listing.currency, listing.in_stock = price, currency, data.in_stock
        listing.confidence_score = Decimal(str(min(data.confidence, match.score if expected_query else data.confidence)))
        listing.extraction_source=data.source; listing.is_active=True; listing.save()
    return listing, None


def _is_homepage_url(url):
    parsed=urlparse(url or ""); path=(parsed.path or "").strip("/").lower()
    if not parsed.netloc or not path: return True
    locale={"fr","en","es","de","it","pt","ar","ru","zh","tr","sw"}
    # A one-segment slug can be a valid product page; only true roots/locales are homepages.
    return path in locale

def _is_category_or_listing_url(url):
    path=(urlparse(url or "").path or "").lower()
    if ".oembed" in path: return True
    return any(t in path for t in ("/categorie/","/category/","/categories/","/collections/","/collection/","/shop/","/search/","/ads/","/annonces/","/market/"))
def _is_comparator_url(url):
    combined=f"{urlparse(url or '').netloc} {urlparse(url or '').path}".lower()
    return any(t in combined for t in ("comparateur","comparison","compare","meilleur-prix","price-comparison"))
def _is_low_quality_source_url(url):
    combined=f"{urlparse(url or '').netloc} {urlparse(url or '').path}".lower()
    return any(t in combined for t in ("forum","blog","reddit","youtube","wikipedia","quora"))
def _collect_search_urls(search_term,max_results):
    urls=[]
    with DDGS() as ddgs:
        for res in ddgs.text(search_term,max_results=max_results):
            url=str(res.get("href") or "").strip()
            if url and not _is_homepage_url(url) and not _is_category_or_listing_url(url) and not _is_comparator_url(url) and not _is_low_quality_source_url(url) and url not in urls: urls.append(url)
    return urls

def cleanup_stale_listings(days=30,product_id=None):
    cutoff=timezone.now()-timezone.timedelta(days=days); qs=PriceListing.objects.filter(scraped_at__lt=cutoff,is_active=True)
    if product_id is not None: qs=qs.filter(product_id=product_id)
    return qs.update(is_active=False)
def _get_sort_rank(item):
    price=item.normalized_price if getattr(item,"normalized_price",None) is not None else item.price
    return (0 if getattr(item,"in_stock",True) else 1,float(price))
def _deduplicate_results(results):
    deduped={}
    for item in results:
        if item is None: continue
        key=(item.product_id,item.retailer_id,item.url)
        if key not in deduped or _get_sort_rank(item)<_get_sort_rank(deduped[key]): deduped[key]=item
    return list(deduped.values())

def search_and_scrape_product(product_query,site_filter="all",model_name=None,max_results=3):
    cleanup_stale_listings(days=getattr(settings,"LISTING_STALE_DAYS",30)); results=[]; errors=[]
    site_filter=(site_filter or "all").strip(); country=getattr(settings,"DEFAULT_SEARCH_COUNTRY","RDC")
    local_domains=getattr(settings,"LOCAL_SEARCH_DOMAINS",["drcmart.com","mobile-rdc.com"]) or []
    if isinstance(local_domains,str): local_domains=[x.strip() for x in local_domains.split(",") if x.strip()]
    site_filters=[x.strip() for x in site_filter.split(",") if x.strip()] if site_filter != "all" else []
    for site in site_filters: ensure_retailer_for_site(site)
    terms=[f"site:{normalize_site_filter(site)[0]} {product_query}" for site in site_filters] if site_filters else [f"site:{d} {product_query} {country} prix" for d in local_domains]+[f"{product_query} {country} acheter prix",f"{product_query} acheter prix",f"{product_query} prix"]
    urls=[]
    # Gather across several search terms instead of stopping after the first local hit.
    target_urls=max(max_results*3,max_results)
    for term in terms:
        try:
            for url in _collect_search_urls(term,max_results):
                if url not in urls: urls.append(url)
        except Exception as exc: errors.append(f"Erreur recherche: {exc}")
        if len(urls)>=target_urls: break
    if not urls: return [], errors or ["Aucune page exploitable n'a été trouvée pour ce produit."]
    allowed=[normalize_site_filter(site)[0] for site in site_filters]
    for url in urls:
        listing,error=process_url_and_save(url,model_name,product_query,allowed)
        if listing: results.append(listing)
        elif error: errors.append(f"{url}: {error}")
    results=_deduplicate_results(results); results.sort(key=_get_sort_rank)
    return results,errors
