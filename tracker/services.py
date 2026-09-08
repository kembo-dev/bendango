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

from tracker.catalog import find_fresh_cached_listings
from tracker.catalog_matching import get_or_create_canonical_product
from tracker.currency import normalize_currency_code
from tracker.extractors import extract_structured_product
from tracker.models import PriceListing, Retailer
from tracker.product_matching import match_product
from tracker.store_discovery import discover_product_urls


class ExtractedProductData(BaseModel):
    product_name: str = Field(description="Nom complet du produit")
    price: float = Field(description="Prix actuel")
    currency: str = Field(description="Code devise")
    in_stock: bool = Field(description="Disponibilité")
    sku_or_ean: str | None = None


def build_fetch_headers():
    return {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"fr-FR,fr;q=0.9,en;q=0.8","Cache-Control":"no-cache"}


def normalize_site_filter(site_filter):
    if site_filter is None:return "all",""
    site=site_filter.strip()
    if not site or site.lower() in {"all","tous","tous les sites"}:return "all",""
    if "://" not in site:site=f"https://{site}"
    parsed=urlparse(site);host=(parsed.netloc or parsed.path).split(":")[0].lower().removeprefix("www.")
    return (host,f"{parsed.scheme}://{parsed.netloc or host}") if host else ("all","")


def ensure_retailer_for_site(site_filter):
    domain,base_url=normalize_site_filter(site_filter)
    if domain=="all" or not base_url:return None
    retailer,_=Retailer.objects.get_or_create(name=domain.capitalize(),defaults={"base_url":base_url})
    if retailer.base_url!=base_url:retailer.base_url=base_url;retailer.save(update_fields=["base_url"])
    return retailer


def get_llm_config():
    configured=getattr(settings,"LLM_CONFIG",{}) or {};default_model=(configured.get("default_model") or os.environ.get("LLM_MODEL") or "").strip()
    if not default_model:raise ImproperlyConfigured("LLM_MODEL must be set in .env.")
    models=configured.get("models") or []
    if not isinstance(models,list):models=[str(models)] if models else []
    if default_model not in models:models.insert(0,default_model)
    return {"provider":(configured.get("provider") or os.environ.get("LLM_PROVIDER") or "bedrock").strip().lower(),"default_model":default_model,"models":models,"region":(configured.get("region") or os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1").strip(),"access_key_id":(configured.get("access_key_id") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("BEDROCK_ACCESS_KEY_ID") or "").strip(),"secret_access_key":(configured.get("secret_access_key") or os.environ.get("AWS_SECRET_ACCESS_KEY") or os.environ.get("BEDROCK_SECRET_ACCESS_KEY") or "").strip(),"session_token":(configured.get("session_token") or os.environ.get("AWS_SESSION_TOKEN") or os.environ.get("BEDROCK_SESSION_TOKEN") or "").strip(),"bearer_token":(configured.get("bearer_token") or os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip(),"base_url":(configured.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "").strip()}


def resolve_bedrock_model_id(model_name,region=None):return (model_name or "").strip()


def fetch_and_clean_html(url):
    session=requests.Session();session.headers.update(build_fetch_headers())
    for attempt in range(3):
        try:
            response=session.get(url,timeout=20,allow_redirects=True)
            if response.status_code in {403,429,500,502,503,504}:raise requests.HTTPError(f"HTTP {response.status_code}")
            response.raise_for_status();break
        except requests.RequestException:
            if attempt==2:return None
            time.sleep(1)
    encoding=response.encoding if isinstance(response.encoding,str) else "utf-8"
    try:text=response.content.decode(encoding,errors="replace")
    except (LookupError,TypeError):text=response.content.decode("utf-8",errors="replace")
    soup=BeautifulSoup(text,"html.parser")
    for element in soup(["style","svg","noscript","header","footer","nav"]):element.decompose()
    return str(soup)[:120000]


def _parse_fallback_price(raw):
    value=raw.replace(" ","").strip()
    if "," in value and "." in value:value=value.replace(".","").replace(",",".") if value.rfind(",")>value.rfind(".") else value.replace(",","")
    elif "," in value:value=value.replace(",",".") if len(value.rsplit(",",1)[1])<=2 else value.replace(",","")
    elif value.count(".")==1 and len(value.rsplit(".",1)[1])>2:value=value.replace(".","")
    return float(value)


def _fallback_extract_html(html_snippet):
    soup=BeautifulSoup(html_snippet,"html.parser");title=soup.title.get_text(" ",strip=True) if soup.title else "";heading=" ".join(n.get_text(" ",strip=True) for n in soup.find_all(["h1","h2","h3"])[:3]);product_name=re.sub(r"\s+"," ",title or heading).strip();text=soup.get_text(" ",strip=True)
    patterns=[r"(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))\s*(?:€|EUR|USD|CDF|FC|\$)",r"(?:€|EUR|USD|CDF|FC|\$)\s*(\d{1,3}(?:[\s\.,]\d{3})*(?:[\.,]\d{1,2}))"]
    raw=next((m.group(1) for p in patterns if (m:=re.search(p,text,flags=re.I))),None)
    if not raw:return None
    currency="CDF" if re.search(r"\bCDF\b|\bFC\b",text,re.I) else "USD" if re.search(r"\bUSD\b|\$",text,re.I) else "EUR";lower=text.lower();stock=not any(t in lower for t in ["rupture","épuisé","epuise","indisponible","out of stock","sold out"])
    return ExtractedProductData(product_name=product_name or "Produit non identifié",price=_parse_fallback_price(raw),currency=currency,in_stock=stock)


def extract_with_ollama(html_snippet,model_name):
    if ollama is None:raise RuntimeError("Le paquet ollama n'est pas installé.")
    response=ollama.chat(model=model_name,messages=[{"role":"system","content":"Tu es un extracteur de données e-commerce précis."},{"role":"user","content":f"Extrais nom, prix, devise, stock et SKU/EAN.\n\nHTML:\n{html_snippet}"}],format=ExtractedProductData.model_json_schema(),options={"temperature":0.1})
    return ExtractedProductData.model_validate_json(response["message"]["content"])


def extract_with_bedrock(html_snippet,model_name):
    if boto3 is None:raise RuntimeError("boto3 n'est pas installé.")
    config=get_llm_config();kwargs={"region_name":config["region"]}
    if config["access_key_id"]:kwargs["aws_access_key_id"]=config["access_key_id"]
    if config["secret_access_key"]:kwargs["aws_secret_access_key"]=config["secret_access_key"]
    if config["session_token"]:kwargs["aws_session_token"]=config["session_token"]
    client=boto3.client("bedrock-runtime",**kwargs);response=client.converse(modelId=resolve_bedrock_model_id(model_name,config["region"]),messages=[{"role":"user","content":[{"text":f"Extrais nom, prix, devise, stock et SKU/EAN en JSON.\n\nHTML:\n{html_snippet}"}]}],inferenceConfig={"temperature":0.1});text="".join(b.get("text","") for b in response.get("output",{}).get("message",{}).get("content",[]) if isinstance(b,dict));return ExtractedProductData.model_validate_json(text) if text else None


def _extract_llm_only(html_snippet,model_name=None):
    config=get_llm_config();selected=(model_name or config["default_model"]).strip()
    try:return extract_with_bedrock(html_snippet,selected) if config["provider"]=="bedrock" else extract_with_ollama(html_snippet,selected)
    except Exception:return None


def extract_with_llm(html_snippet,model_name=None):return _extract_llm_only(html_snippet,model_name) or _fallback_extract_html(html_snippet)


def _structured_to_extracted(html,query=None):
    s=extract_structured_product(html,query=query)
    if s is None:return None,""
    return ExtractedProductData(product_name=s.product_name,price=float(s.price),currency=s.currency,in_stock=s.in_stock,sku_or_ean=s.sku_or_ean),(s.source or "unknown")


def _confidence_for(source,match_score,has_sku):
    base={"jsonld":.92,"shopify":.88,"meta":.84,"llm":.76,"html":.62,"cache":.70}.get(source,.55);score=base+(.04 if has_sku else 0)+(.04*max(0,min(match_score,1)));return Decimal(str(round(min(score,.99),4)))


def _cached_listing_for_url(url,expected_query=None):
    listing=PriceListing.objects.select_related("product","retailer").filter(url=url,is_active=True).order_by("-scraped_at").first()
    if listing is None:return None
    if expected_query and not match_product(expected_query,listing.product.name).is_match:return None
    return listing


def _deactivate_listing_for_url(url):return PriceListing.objects.filter(url=url,is_active=True).update(is_active=False)

def _is_not_found_page(html):return bool(html) and any(m in html.lower() for m in ["404 page introuvable","page introuvable","not found","page not found","could not find this page","we couldn't find this page"])

def _has_exploitable_product_structure(html):
    if not html:return False
    soup=BeautifulSoup(html,"html.parser");text=soup.get_text(" ",strip=True)
    if len(text)<40:return False
    lower=text.lower();price=bool(re.search(r"(?:€|eur|usd|cdf|fc|\$)\s*\d|\d[\d\s\.,]*\s*(?:€|eur|usd|cdf|fc|\$)",text,re.I));signal=any(t in lower for t in ["prix","price","en stock","in stock","sku","ean","product","produit","ajouter au panier","add to cart","acheter","buy now"])
    return signal and len(soup.find_all(["h1","h2","h3","p","div","span"]))>=2 and not (any(t in lower for t in ["bienvenue","newsletter","contact","blog"]) and not price)


def process_url_and_save(url,model_name=None,expected_query=None,allowed_hosts=None):
    parsed=urlparse(url)
    if _is_homepage_url(url):return None,"URL de page d'accueil non exploitable pour un produit."
    if _is_category_or_listing_url(url):return None,"URL de liste ou catégorie non exploitable pour un produit unique."
    if _is_low_quality_source_url(url):return None,"Source non marchande ignorée."
    cached=_cached_listing_for_url(url,expected_query);html=fetch_and_clean_html(url)
    if not html:return (cached,None) if cached else (None,"Impossible de récupérer le contenu de la page web.")
    if _is_not_found_page(html):_deactivate_listing_for_url(url);return None,"Page introuvable ou URL produit inexistante."
    extracted,source=_structured_to_extracted(html,query=expected_query)
    if extracted is None and expected_query and not _has_exploitable_product_structure(html):return (cached,None) if cached else (None,"Page sans structure de produit exploitable.")
    if extracted is None:extracted=_extract_llm_only(html,model_name);source="llm" if extracted else "html";extracted=extracted or _fallback_extract_html(html)
    if not extracted:return (cached,None) if cached else (None,"L'extraction a échoué.")
    name=(extracted.product_name or "").strip();currency=normalize_currency_code(extracted.currency);price=Decimal(str(extracted.price)).quantize(Decimal("0.01"))
    if not name or name.lower() in {"unknown","inconnu","n/a","na"} or price<=0:return (cached,None) if cached else (None,"Données extraites invalides ou page non exploitable.")
    match=match_product(expected_query,name) if expected_query else None
    if match and not match.is_match:return (cached,None) if cached else (None,f"Produit non pertinent ({match.reason}, score={match.score:.2f}).")
    match_score=match.score if match else 1.0;host=(parsed.netloc or "").lower().removeprefix("www.");base=f"{parsed.scheme}://{parsed.netloc}"
    with transaction.atomic():
        retailer,_=Retailer.objects.get_or_create(name=(host or "Site inconnu").capitalize(),defaults={"base_url":base})
        if retailer.base_url!=base:retailer.base_url=base;retailer.save(update_fields=["base_url"])
        if cached:product=cached.product;canonical_score=1.0
        else:product,canonical=get_or_create_canonical_product(name,sku_or_ean=extracted.sku_or_ean);canonical_score=canonical.score
        listing=PriceListing.objects.filter(product=product,retailer=retailer,url=url).first() or cached or PriceListing(product=product,retailer=retailer,url=url)
        listing.product=product;listing.retailer=retailer;listing.price=price;listing.currency=currency;listing.in_stock=extracted.in_stock;listing.is_active=True;listing.extraction_source=source or "unknown";listing.match_score=Decimal(str(round(min(match_score,canonical_score),4)));listing.confidence_score=_confidence_for(source,match_score,bool(extracted.sku_or_ean));listing.save()
    return listing,None


def _is_homepage_url(url):
    if not url:return True
    parsed=urlparse(url)
    if not parsed.netloc:return True
    path=(parsed.path or "").strip("/").lower()
    if not path or path in {"fr","en","es","de","it","pt","ar","ru","zh","tr","sw"}:return True
    parts=[p for p in path.split("/") if p];return len(parts)==1 and parts[0] not in {"products","product","produits","produit"}


def _is_category_or_listing_url(url):
    path=(urlparse(url).path or "").lower()
    return ".oembed" in path or path.endswith("/oembed") or any(t in path for t in ("/categorie/","/category/","/categories/","/collections/","/collection/","/shop/","/search/","/ads/","/annonces/","/market/","/en/ads/"))

def _is_comparator_url(url):
    combined=f"{urlparse(url).netloc} {urlparse(url).path}".lower();return any(t in combined for t in ["comparateur","comparaison","compare","comparison","meilleur-prix","best-price","price-comparison","pricecomparison"])

def _is_low_quality_source_url(url):
    parsed=urlparse(url);host=parsed.netloc.lower().removeprefix("www.");path=parsed.path.lower();blocked=("facebook.com","fb.com","instagram.com","tiktok.com","x.com","twitter.com","pinterest.com","youtube.com","youtu.be","reddit.com","quora.com","wikipedia.org","archive.org","web.archive.org","linkedin.com","discord.com","discord.gg","telegram.org","t.me","whatsapp.com")
    if any(host==b or host.endswith("."+b) for b in blocked):return True
    if path.endswith((".txt",".pdf",".epub",".doc",".docx",".xml",".csv",".zip")):return True
    return any(t in f"{host} {path}" for t in ["/forum/","/forums/","/blog/","/discussion/","/topic/","/wiki/","/stream/"])


def _collect_search_urls(search_term,max_results):
    urls=[]
    with DDGS() as ddgs:
        for result in ddgs.text(search_term,max_results=max_results):
            url=str(result.get("href") or "").strip()
            if url and not (_is_homepage_url(url) or _is_category_or_listing_url(url) or _is_comparator_url(url) or _is_low_quality_source_url(url)) and url not in urls:urls.append(url)
    return urls


def cleanup_stale_listings(days=30,product_id=None):
    cutoff=timezone.now()-timezone.timedelta(days=days);q=PriceListing.objects.filter(scraped_at__lt=cutoff,is_active=True)
    if product_id is not None:q=q.filter(product_id=product_id)
    return q.update(is_active=False)

def _get_sort_rank(item):
    normalized=getattr(item,"normalized_price",None);price=normalized if normalized is not None else getattr(item,"price",0);return (0 if getattr(item,"in_stock",True) else 1,float(price))

def _deduplicate_results(results):
    deduped={}
    for item in results:
        if item is None:continue
        url=getattr(item,"url","");key=(getattr(item,"product_id",None),getattr(item,"retailer_id",None),url) if url else (id(item),)
        if key not in deduped or _get_sort_rank(item)<_get_sort_rank(deduped[key]):deduped[key]=item
    return list(deduped.values())


def _known_merchant_domains(limit=20):
    """Use accumulated merchant knowledge as fallback, never as a discovery allowlist."""
    domains=[]
    for base_url in Retailer.objects.filter(is_active=True).order_by("-trust_score").values_list("base_url",flat=True)[:limit]:
        host=urlparse(base_url).netloc.lower().removeprefix("www.")
        if host and host not in domains:domains.append(host)
    return domains


def search_and_scrape_product(product_query,site_filter="all",model_name=None,max_results=3):
    cleanup_stale_listings(days=getattr(settings,"LISTING_STALE_DAYS",30));selected=(model_name or get_llm_config()["default_model"]).strip();results=[];errors=[];site_filter=(site_filter or "all").strip() or "all";country=getattr(settings,"DEFAULT_SEARCH_COUNTRY","RDC");site_filters=[] if site_filter=="all" else [p.strip() for p in site_filter.split(",") if p.strip()]
    for site in site_filters:ensure_retailer_for_site(site)
    cache_hosts=[normalize_site_filter(site)[0] for site in site_filters];cached=find_fresh_cached_listings(product_query,site_hosts=cache_hosts)
    if cached:return cached,[]

    if site_filters:
        search_terms=[f"site:{normalize_site_filter(site)[0]} {product_query}" for site in site_filters]
    else:
        # Open-web discovery first. No merchant is privileged or required.
        search_terms=[f'"{product_query}" {country} prix acheter',f'"{product_query}" Kinshasa prix',f'{product_query} {country} boutique en ligne',f'{product_query} acheter prix',f'{product_query} prix']

    urls=[];search_errors=[];candidate_limit=max(max_results*4,12)
    for term in search_terms:
        try:found=_collect_search_urls(term,max_results=candidate_limit)
        except Exception as exc:search_errors.append(str(exc));continue
        for url in found:
            if url not in urls:urls.append(url)
        # Do not stop after the first search engine hit: diversify merchants.
        if len(urls)>=candidate_limit:break

    allowed_hosts=[normalize_site_filter(site)[0] for site in site_filters]
    for url in urls:
        listing,error=process_url_and_save(url,model_name=selected,expected_query=product_query,allowed_hosts=allowed_hosts)
        if listing:results.append(listing)
        elif error and error!="Source non marchande ignorée.":errors.append(f"{url}: {error}")
        if len(_deduplicate_results(results))>=max_results and not site_filters:break

    # If open-web candidates were poor, search merchant domains learned from the DB.
    if len(_deduplicate_results(results))<max_results:
        fallback_domains=cache_hosts or _known_merchant_domains()
        if fallback_domains:
            try:fallback_urls=discover_product_urls(product_query,fallback_domains,max_results=max_results*2)
            except Exception as exc:search_errors.append(str(exc));fallback_urls=[]
            for url in fallback_urls:
                if url in urls:continue
                listing,error=process_url_and_save(url,model_name=selected,expected_query=product_query,allowed_hosts=allowed_hosts)
                if listing:results.append(listing)
                elif error and error!="Source non marchande ignorée.":errors.append(f"{url}: {error}")
                if len(_deduplicate_results(results))>=max_results:break

    results=_deduplicate_results(results);results.sort(key=_get_sort_rank)
    if results:return results,[]
    if search_errors and not urls:return [],["La recherche web n'a retourné aucune page marchande exploitable pour ce produit."]
    return [],errors or ["Aucune page marchande exploitable n'a été trouvée pour ce produit."]
