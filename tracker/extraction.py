import json
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

from tracker.currency import normalize_currency


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def extract_jsonld_product(html: str) -> dict | None:
    """Return normalized schema.org Product data when the page exposes it."""
    soup = BeautifulSoup(html or "", "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        for node in _walk_json(payload):
            node_type = node.get("@type")
            types = node_type if isinstance(node_type, list) else [node_type]
            if not any(str(item).lower() == "product" for item in types if item):
                continue

            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = next((offer for offer in offers if isinstance(offer, dict)), {})
            if not isinstance(offers, dict):
                offers = {}

            raw_price = offers.get("price") or offers.get("lowPrice")
            currency = normalize_currency(offers.get("priceCurrency"))
            try:
                price = Decimal(str(raw_price))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if price <= 0 or currency is None:
                continue

            availability = str(offers.get("availability") or "").lower()
            in_stock = not any(token in availability for token in ("outofstock", "soldout", "discontinued"))
            sku = node.get("sku") or node.get("gtin13") or node.get("gtin") or node.get("mpn")
            brand = node.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")

            return {
                "product_name": str(node.get("name") or "").strip(),
                "price": float(price),
                "currency": currency,
                "in_stock": in_stock,
                "sku_or_ean": str(sku).strip() if sku else None,
                "brand": str(brand).strip() if brand else "",
                "image_url": _first_image(node.get("image")),
                "source": "jsonld",
                "confidence": 0.98,
            }
    return None


def _first_image(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else ""
    if isinstance(value, dict):
        return str(value.get("url") or value.get("contentUrl") or "")
    return ""
