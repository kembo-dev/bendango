import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from tracker.currency import normalize_currency_code
from tracker.product_matching import match_product


@dataclass(frozen=True)
class StructuredProductData:
    product_name: str
    price: Decimal
    currency: str
    in_stock: bool
    sku_or_ean: str | None = None
    brand: str = ""
    image_url: str = ""
    source: str = "unknown"


def _decimal_price(value) -> Decimal | None:
    if value is None:
        return None
    raw = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) <= 2 else raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    raw = re.sub(r"[^0-9.]", "", raw)
    try:
        price = Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
    return price if price > 0 else None


def _shopify_variant_price(value) -> Decimal | None:
    """Decode Shopify variant prices, which are commonly integer cents."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+", raw):
        amount = Decimal(raw)
        # Shopify product/variant JSON uses the smallest currency unit.
        return (amount / Decimal("100")).quantize(Decimal("0.01")) if amount >= 100 else amount
    return _decimal_price(raw)


def _iter_jsonld_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(value, dict):
        yield value
        if value.get("@graph"):
            yield from _iter_jsonld_nodes(value["@graph"])


def _type_contains_product(value) -> bool:
    product_type = value.get("@type")
    if isinstance(product_type, list):
        return any(str(item).lower() == "product" for item in product_type)
    return str(product_type or "").lower() == "product"


def _first_offer(offers):
    if isinstance(offers, list):
        return next((item for item in offers if isinstance(item, dict)), {})
    return offers if isinstance(offers, dict) else {}


def extract_jsonld_product(html: str) -> StructuredProductData | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text("", strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld_nodes(payload):
            if not _type_contains_product(node):
                continue
            offer = _first_offer(node.get("offers"))
            price = _decimal_price(offer.get("price") or offer.get("lowPrice") or node.get("price"))
            name = str(node.get("name") or "").strip()
            if not name or price is None:
                continue
            availability = str(offer.get("availability") or "").lower()
            in_stock = not any(token in availability for token in ("outofstock", "soldout", "discontinued"))
            currency = normalize_currency_code(offer.get("priceCurrency") or node.get("priceCurrency") or "USD")
            brand = node.get("brand") or ""
            if isinstance(brand, dict):
                brand = brand.get("name") or ""
            image = node.get("image") or ""
            if isinstance(image, list):
                image = image[0] if image else ""
            elif isinstance(image, dict):
                image = image.get("url") or image.get("contentUrl") or ""
            sku = node.get("sku") or node.get("gtin13") or node.get("gtin12") or node.get("gtin") or node.get("mpn")
            return StructuredProductData(name, price, currency, in_stock, str(sku).strip() if sku else None, str(brand).strip(), str(image).strip(), "jsonld")
    return None


def extract_meta_product(html: str) -> StructuredProductData | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")

    def meta(*keys):
        for key in keys:
            tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"itemprop": key})
            if tag and tag.get("content"):
                return tag.get("content").strip()
        return ""

    name = meta("og:title", "twitter:title", "name")
    price = _decimal_price(meta("product:price:amount", "og:price:amount", "price"))
    if not name or price is None:
        return None
    currency = normalize_currency_code(meta("product:price:currency", "og:price:currency", "priceCurrency") or "USD")
    availability = meta("product:availability", "availability").lower()
    in_stock = not any(token in availability for token in ("out of stock", "outofstock", "sold out", "soldout"))
    return StructuredProductData(name, price, currency, in_stock, meta("product:retailer_item_id", "sku") or None, meta("product:brand", "brand"), meta("og:image", "twitter:image"), "meta")


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def extract_shopify_product(html: str, query: str | None = None) -> StructuredProductData | None:
    """Extract Shopify product objects embedded in JSON/script payloads."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for script in soup.find_all("script"):
        raw = script.string or script.get_text("", strip=True)
        if not raw or len(raw) > 500000:
            continue
        payloads = []
        if script.get("type") in {"application/json", "application/ld+json"}:
            try:
                payloads.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                pass
        # Shopify themes also embed JSON objects inside JS assignments.
        for match in re.finditer(r"\{[^{}]{0,2500}\"variants\"\s*:\s*\[[^\]]+\][^{}]{0,2500}\}", raw, re.S):
            try:
                payloads.append(json.loads(match.group(0)))
            except (json.JSONDecodeError, TypeError):
                continue

        for payload in payloads:
            for node in _walk_dicts(payload):
                title = str(node.get("title") or node.get("name") or "").strip()
                variants = node.get("variants")
                if not title or not isinstance(variants, list) or not variants:
                    continue
                if query:
                    match = match_product(query, title, threshold=0.72)
                    if not match.is_match:
                        continue
                    score = match.score
                else:
                    score = 1.0

                prices = []
                selected_variant = None
                for variant in variants:
                    if not isinstance(variant, dict):
                        continue
                    price = _shopify_variant_price(variant.get("price"))
                    if price is not None:
                        prices.append(price)
                        if selected_variant is None or price < _shopify_variant_price(selected_variant.get("price")):
                            selected_variant = variant
                if not prices:
                    continue

                selected_variant = selected_variant or variants[0]
                sku = selected_variant.get("sku") if isinstance(selected_variant, dict) else None
                available = bool(selected_variant.get("available", True)) if isinstance(selected_variant, dict) else True
                image = node.get("featured_image") or node.get("image") or ""
                if isinstance(image, dict):
                    image = image.get("src") or image.get("url") or ""
                candidates.append((score, StructuredProductData(
                    product_name=title,
                    price=min(prices),
                    currency="USD",
                    in_stock=available,
                    sku_or_ean=str(sku).strip() if sku else None,
                    image_url=str(image).strip(),
                    source="shopify",
                )))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _currency_from_text(text: str) -> str:
    if re.search(r"\b(?:CDF|FC)\b|₣", text, re.I):
        return "CDF"
    if "$" in text or re.search(r"\bUSD\b", text, re.I):
        return "USD"
    if "€" in text or re.search(r"\bEUR\b", text, re.I):
        return "EUR"
    return "USD"


def _price_candidates_from_node(node) -> list[Decimal]:
    values = []
    if node is None:
        return values
    for sale_node in node.select("ins .woocommerce-Price-amount, ins .amount, ins"):
        price = _decimal_price(sale_node.get_text(" ", strip=True))
        if price is not None:
            values.append(price)
    if values:
        return values
    for price_node in node.select(".woocommerce-Price-amount, .amount, [itemprop='price'], .price"):
        price = _decimal_price(price_node.get("content") or price_node.get_text(" ", strip=True))
        if price is not None:
            values.append(price)
    return values


def _infer_name_from_content(soup: BeautifulSoup) -> str:
    patterns = [
        r"quel est le prix de l[’']?\s*([^?]+?)\s+à\s+kinshasa",
        r"la sortie de l[’']?\s*([^!.]+?)\s+à\s+kinshasa",
        r"l[’']?\s*(iphone\s+[0-9a-z+\- ]+?)\s+à\s+kinshasa",
    ]
    candidates = []
    for node in soup.find_all(["h2", "h3", "p"], limit=80):
        text = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()
        if text:
            candidates.append(text)
    combined = " ".join(candidates)
    for pattern in patterns:
        match = re.search(pattern, combined, re.I)
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip(" .:-")
            if name:
                return name
    return ""


def _checkout_price_from_text(text: str) -> Decimal | None:
    markers = ["Commander sur WhatsApp", "Ajouter au panier", "VENTE FLASH", "Vente flash"]
    for marker in markers:
        index = text.lower().find(marker.lower())
        if index == -1:
            continue
        window = text[max(0, index - 300):min(len(text), index + 120)]
        matches = re.findall(r"(?:\$|USD|CDF|FC|€)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(?:\$|USD|CDF|FC|€)", window, re.I)
        prices = [_decimal_price(left or right) for left, right in matches]
        prices = [price for price in prices if price is not None]
        if prices:
            return prices[-1]
    return None


def extract_woocommerce_product(html: str) -> StructuredProductData | None:
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    name_node = soup.select_one("h1.product_title") or soup.select_one(".summary h1") or soup.select_one("main h1") or soup.find("h1")
    name = name_node.get_text(" ", strip=True) if name_node else ""
    if not name or name in {"…", "..."}:
        meta_title = soup.find("meta", attrs={"property": "og:title"})
        name = meta_title.get("content", "").strip() if meta_title else ""
    if not name or name in {"…", "..."}:
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        if title:
            name = re.sub(r"\s*[|–—-]\s*Mobile\s*RDC.*$", "", title, flags=re.I).strip()
    if not name or name in {"…", "..."}:
        name = _infer_name_from_content(soup)
    if not name:
        return None
    primary = soup.select_one(".summary.entry-summary") or soup.select_one(".summary") or soup.select_one("div.product.type-product") or soup.select_one("main") or soup.body
    if primary is None:
        return None
    primary_text = primary.get_text(" ", strip=True)
    price = _checkout_price_from_text(primary_text)
    if price is None:
        prices = _price_candidates_from_node(primary)
        if not prices:
            for raw in re.findall(r"(?:USD\s*)?(\d[\d\s.,]*)\s*(?:\$|USD|CDF|FC|€)", primary_text, re.I):
                parsed = _decimal_price(raw)
                if parsed is not None:
                    prices.append(parsed)
        if not prices:
            return None
        price = prices[0]
    lowered = primary_text.lower()
    sku_node = primary.select_one(".sku, [itemprop='sku']") if hasattr(primary, "select_one") else None
    image_node = soup.select_one(".woocommerce-product-gallery img, .product img")
    return StructuredProductData(
        name, price, normalize_currency_code(_currency_from_text(primary_text)),
        not any(token in lowered for token in ("rupture", "out of stock", "sold out", "indisponible")),
        sku_node.get_text(" ", strip=True) if sku_node else None,
        image_url=((image_node.get("data-large_image") or image_node.get("src") or "").strip() if image_node else ""),
        source="html",
    )


def _query_from_document_url(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if canonical and canonical.get("href"):
        candidates.append(canonical.get("href"))
    og_url = soup.find("meta", attrs={"property": "og:url"})
    if og_url and og_url.get("content"):
        candidates.append(og_url.get("content"))
    for url in candidates:
        path = unquote(urlparse(url).path)
        match = re.search(r"/products/([^/?#]+)", path, re.I)
        if match:
            return re.sub(r"\s+", " ", match.group(1).replace("-", " ").replace("_", " ")).strip()
    return ""


def extract_matching_product_card(html: str, query: str) -> StructuredProductData | None:
    if not html or not query:
        return None
    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_score = 0.0
    for link in soup.select("a[href*='/products/']"):
        title = link.get_text(" ", strip=True) or link.get("title", "").strip()
        if not title:
            continue
        result = match_product(query, title, threshold=0.72)
        if not result.is_match or result.score <= best_score:
            continue
        card = link
        for _ in range(5):
            parent = getattr(card, "parent", None)
            if parent is None:
                break
            card = parent
            if re.search(r"(?:\$|USD|CDF|FC|€)\s*\d|\d[\d\s.,]*\s*(?:\$|USD|CDF|FC|€)", card.get_text(" ", strip=True), re.I):
                break
        card_text = card.get_text(" ", strip=True)
        matches = re.findall(r"(?:\$|USD|CDF|FC|€)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(?:\$|USD|CDF|FC|€)", card_text, re.I)
        prices = [_decimal_price(left or right) for left, right in matches]
        prices = [price for price in prices if price is not None]
        if not prices:
            continue
        image_node = card.find("img") if hasattr(card, "find") else None
        best = StructuredProductData(
            title, min(prices), normalize_currency_code(_currency_from_text(card_text)), True,
            image_url=((image_node.get("src") or image_node.get("data-src") or "").strip() if image_node else ""), source="html",
        )
        best_score = result.score
    return best


def _candidate_matches_query(candidate: StructuredProductData | None, query: str) -> bool:
    if candidate is None:
        return False
    if not query:
        return True
    return match_product(query, candidate.product_name, threshold=0.72).is_match


def extract_structured_product(html: str, query: str | None = None) -> StructuredProductData | None:
    inferred_query = query or _query_from_document_url(html)
    for candidate in (
        extract_jsonld_product(html),
        extract_meta_product(html),
        extract_shopify_product(html, inferred_query),
        extract_woocommerce_product(html),
    ):
        if candidate is None:
            continue
        if not inferred_query or _candidate_matches_query(candidate, inferred_query):
            return candidate
    return extract_matching_product_card(html, inferred_query) if inferred_query else None
