from __future__ import annotations

import re
from dataclasses import dataclass

from tracker.models import Product
from tracker.product_matching import match_product, normalize_product_name


VARIANT_TOKENS = {"pro", "max", "plus", "ultra", "mini", "lite", "fe", "se"}
STORAGE_RE = re.compile(r"\b(\d+)\s*(gb|go|tb|to|mb)\b", re.IGNORECASE)
RAM_RE = re.compile(r"\b(\d+)\s*(gb|go)\s*(?:ram)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalResolution:
    product: Product | None
    score: float
    reason: str


def _variant_tokens(name: str) -> set[str]:
    return set(normalize_product_name(name).split()) & VARIANT_TOKENS


def _storage_tokens(name: str) -> set[str]:
    normalized = normalize_product_name(name)
    return {f"{amount}{unit}" for amount, unit in STORAGE_RE.findall(normalized)}


def _has_variant_conflict(left: str, right: str) -> bool:
    left_variants = _variant_tokens(left)
    right_variants = _variant_tokens(right)
    if left_variants != right_variants and (left_variants or right_variants):
        return True

    left_storage = _storage_tokens(left)
    right_storage = _storage_tokens(right)
    if left_storage and right_storage and left_storage.isdisjoint(right_storage):
        return True
    return False


def resolve_canonical_product(
    product_name: str,
    *,
    sku_or_ean: str | None = None,
    minimum_score: float = 0.82,
) -> CanonicalResolution:
    """Resolve an extracted merchant title to an existing canonical Product.

    Resolution order:
    1. exact SKU/EAN;
    2. exact normalized title;
    3. conservative V3 title matching without variant/storage conflicts.
    """
    name = (product_name or "").strip()
    sku = (sku_or_ean or "").strip()
    if sku:
        product = Product.objects.filter(sku_or_ean=sku).first()
        if product:
            return CanonicalResolution(product, 1.0, "sku/ean identique")

    normalized = normalize_product_name(name)
    if not normalized:
        return CanonicalResolution(None, 0.0, "nom produit vide")

    best_product = None
    best_score = 0.0
    best_reason = "aucun produit canonique compatible"

    for product in Product.objects.all().only("id", "name", "sku_or_ean"):
        if normalize_product_name(product.name) == normalized:
            return CanonicalResolution(product, 1.0, "nom normalisé identique")

        if _has_variant_conflict(name, product.name):
            continue

        result = match_product(name, product.name, threshold=minimum_score)
        if result.is_match and result.score > best_score:
            best_product = product
            best_score = result.score
            best_reason = result.reason

    if best_product is None:
        return CanonicalResolution(None, 0.0, best_reason)
    return CanonicalResolution(best_product, best_score, best_reason)


def get_or_create_canonical_product(
    product_name: str,
    *,
    sku_or_ean: str | None = None,
) -> tuple[Product, CanonicalResolution]:
    resolution = resolve_canonical_product(product_name, sku_or_ean=sku_or_ean)
    if resolution.product is not None:
        product = resolution.product
        if sku_or_ean and not product.sku_or_ean:
            product.sku_or_ean = sku_or_ean
            product.save(update_fields=["sku_or_ean", "updated_at"])
        return product, resolution

    product = Product.objects.create(
        name=(product_name or "Produit non identifié").strip(),
        sku_or_ean=(sku_or_ean or None),
    )
    return product, CanonicalResolution(product, 1.0, "nouveau produit canonique")
