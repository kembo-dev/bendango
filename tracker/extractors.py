import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from tracker.currency import normalize_currency_code


@dataclass(frozen=True)
class StructuredProductData:
    product_name: str
    price: Decimal
    currency: str
    in_stock: bool
    sku_or_ean: str | None = None
    brand: str = ""
    image_url: str = ""


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
    """Extract schema.org Product/Offer data before any script cleanup."""
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
            )

    return None


def extract_meta_product(html: str) -> StructuredProductData | None:
    """Fallback to OpenGraph/product meta tags when JSON-LD is unavailable."""
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
    )


def extract_structured_product(html: str) -> StructuredProductData | None:
    return extract_jsonld_product(html) or extract_meta_product(html)
