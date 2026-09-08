import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

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


def _iter_jsonld_nodes(value):
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph:
            yield from _iter_jsonld_nodes(graph)


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
            return StructuredProductData(
                product_name=name,
                price=price,
                currency=currency,
                in_stock=in_stock,
                sku_or_ean=str(sku).strip() if sku else None,
                brand=str(brand).strip(),
                image_url=str(image).strip(),
                source="jsonld",
            )

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

    return StructuredProductData(
        product_name=name,
        price=price,
        currency=currency,
        in_stock=in_stock,
        sku_or_ean=meta("product:retailer_item_id", "sku") or None,
        brand=meta("product:brand", "brand"),
        image_url=meta("og:image", "twitter:image"),
        source="meta",
    )


def _currency_from_text(text: str) -> str:
    if re.search(r"\b(?:CDF|FC)\b|₣", text, re.I):
        return "CDF"
    if "$" in text or re.search(r"\bUSD\b", text, re.I):
        return "USD"
    if "€" in text or re.search(r"\bEUR\b", text, re.I):
        return "EUR"
    return "USD"


def _price_candidates_from_node(node) -> list[Decimal]:
    values: list[Decimal] = []
    if node is None:
        return values

    sale_nodes = node.select("ins .woocommerce-Price-amount, ins .amount, ins")
    for sale_node in sale_nodes:
        price = _decimal_price(sale_node.get_text(" ", strip=True))
        if price is not None:
            values.append(price)
    if values:
        return values

    for price_node in node.select(".woocommerce-Price-amount, .amount, [itemprop='price'], .price"):
        raw = price_node.get("content") or price_node.get_text(" ", strip=True)
        price = _decimal_price(raw)
        if price is not None:
            values.append(price)
    return values


def extract_woocommerce_product(html: str) -> StructuredProductData | None:
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    name_node = (
        soup.select_one("h1.product_title")
        or soup.select_one(".summary h1")
        or soup.select_one("main h1")
        or soup.find("h1")
    )
    name = name_node.get_text(" ", strip=True) if name_node else ""
    if not name or name in {"…", "..."}:
        meta_title = soup.find("meta", attrs={"property": "og:title"})
        name = meta_title.get("content", "").strip() if meta_title else ""
    if not name:
        return None

    primary = (
        soup.select_one(".summary.entry-summary")
        or soup.select_one(".summary")
        or soup.select_one("div.product.type-product")
        or soup.select_one("main")
    )
    if primary is None:
        return None

    price_values = _price_candidates_from_node(primary)
    if not price_values:
        text = primary.get_text(" ", strip=True)
        for raw in re.findall(r"(?:USD\s*)?(\d[\d\s.,]*)\s*(?:\$|USD|CDF|FC|€)", text, re.I):
            price = _decimal_price(raw)
            if price is not None:
                price_values.append(price)

    if not price_values:
        return None

    price = price_values[0]
    primary_text = primary.get_text(" ", strip=True)
    currency = normalize_currency_code(_currency_from_text(primary_text))
    lowered = primary_text.lower()
    in_stock = not any(token in lowered for token in ("rupture", "out of stock", "sold out", "indisponible"))

    sku_node = primary.select_one(".sku, [itemprop='sku']")
    sku = sku_node.get_text(" ", strip=True) if sku_node else None

    image = ""
    image_node = soup.select_one(".woocommerce-product-gallery img, .product img")
    if image_node:
        image = (image_node.get("data-large_image") or image_node.get("src") or "").strip()

    return StructuredProductData(
        product_name=name,
        price=price,
        currency=currency,
        in_stock=in_stock,
        sku_or_ean=sku or None,
        image_url=image,
        source="html",
    )


def extract_matching_product_card(html: str, query: str) -> StructuredProductData | None:
    """Recover a matching product from Shopify/search/collection cards.

    Useful when a stale product URL renders a 404 or recommendation template but
    the storefront still exposes the requested product elsewhere in the HTML.
    """
    if not html or not query:
        return None

    soup = BeautifulSoup(html, "html.parser")
    best = None
    best_score = 0.0

    links = soup.select("a[href*='/products/']")
    for link in links:
        title = link.get_text(" ", strip=True)
        if not title:
            title = link.get("title", "").strip()
        if not title:
            continue

        match = match_product(query, title, threshold=0.72)
        if not match.is_match or match.score <= best_score:
            continue

        card = link
        for _ in range(5):
            parent = getattr(card, "parent", None)
            if parent is None:
                break
            card = parent
            text = card.get_text(" ", strip=True)
            if re.search(r"(?:\$|USD|CDF|FC|€)\s*\d|\d[\d\s.,]*\s*(?:\$|USD|CDF|FC|€)", text, re.I):
                break

        card_text = card.get_text(" ", strip=True)
        price_matches = re.findall(
            r"(?:\$|USD|CDF|FC|€)\s*([0-9][0-9\s.,]*)|([0-9][0-9\s.,]*)\s*(?:\$|USD|CDF|FC|€)",
            card_text,
            re.I,
        )
        prices = []
        for left, right in price_matches:
            price = _decimal_price(left or right)
            if price is not None:
                prices.append(price)
        if not prices:
            continue

        # Shopify sale cards generally display the current price first, followed
        # by the compare-at price. Choose the smallest positive value defensively.
        price = min(prices)
        currency = normalize_currency_code(_currency_from_text(card_text))
        image = ""
        image_node = card.find("img") if hasattr(card, "find") else None
        if image_node:
            image = (image_node.get("src") or image_node.get("data-src") or "").strip()

        best = StructuredProductData(
            product_name=title,
            price=price,
            currency=currency,
            in_stock=True,
            image_url=image,
            source="html",
        )
        best_score = match.score

    return best


def extract_structured_product(html: str, query: str | None = None) -> StructuredProductData | None:
    return (
        extract_jsonld_product(html)
        or extract_meta_product(html)
        or extract_woocommerce_product(html)
        or (extract_matching_product_card(html, query) if query else None)
    )
