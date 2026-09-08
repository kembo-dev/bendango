from __future__ import annotations

import re
from dataclasses import dataclass

from tracker.models import Product
from tracker.product_matching import match_product, normalize_product_name


VARIANT_TOKENS = {"pro", "max", "plus", "ultra", "mini", "lite", "fe", "se"}
CAPACITY_RE = re.compile(r"\b(\d+)\s*(gb|go|tb|to|mb)\b", re.IGNORECASE)
RAM_AFTER_RE = re.compile(r"\b(\d+)\s*(gb|go)\s*(?:de\s+)?ram\b", re.IGNORECASE)
RAM_BEFORE_RE = re.compile(r"\bram\s*(\d+)\s*(gb|go)\b", re.IGNORECASE)
COMPACT_RE = re.compile(r"\b(\d{1,2})\s*(?:gb|go)?\s*[+/]\s*(\d{2,4})\s*(gb|go|tb|to)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class CanonicalResolution:
    product: Product | None
    score: float
    reason: str


@dataclass(frozen=True)
class CapacityProfile:
    ram_gb: int | None = None
    storage_gb: int | None = None


def _variant_tokens(name: str) -> set[str]:
    return set(normalize_product_name(name).split()) & VARIANT_TOKENS


def _to_gb(amount: str, unit: str | None) -> int | None:
    value = int(amount)
    normalized = (unit or "gb").lower()
    if normalized in {"tb", "to"}:
        return value * 1024
    if normalized in {"gb", "go"}:
        return value
    return None


def capacity_profile(name: str) -> CapacityProfile:
    text = (name or "").lower()

    compact = COMPACT_RE.search(text)
    if compact:
        ram = int(compact.group(1))
        storage = _to_gb(compact.group(2), compact.group(3))
        if ram <= 64 and storage is not None and storage > ram:
            return CapacityProfile(ram_gb=ram, storage_gb=storage)

    explicit_ram = None
    ram_match = RAM_AFTER_RE.search(text) or RAM_BEFORE_RE.search(text)
    if ram_match:
        explicit_ram = _to_gb(ram_match.group(1), ram_match.group(2))

    capacities = []
    for amount, unit in CAPACITY_RE.findall(text):
        value = _to_gb(amount, unit)
        if value is not None:
            capacities.append(value)

    unique = sorted(set(capacities))
    if explicit_ram is not None:
        storage_candidates = [value for value in unique if value != explicit_ram]
        return CapacityProfile(explicit_ram, max(storage_candidates) if storage_candidates else None)

    if len(unique) >= 2:
        smallest, largest = unique[0], unique[-1]
        if smallest <= 64 and largest > smallest:
            return CapacityProfile(ram_gb=smallest, storage_gb=largest)
        return CapacityProfile(storage_gb=largest)

    if len(unique) == 1:
        value = unique[0]
        return CapacityProfile(storage_gb=value if value > 64 else None)

    return CapacityProfile()


def has_variant_conflict(left: str, right: str) -> bool:
    left_variants = _variant_tokens(left)
    right_variants = _variant_tokens(right)
    if left_variants != right_variants and (left_variants or right_variants):
        return True

    left_capacity = capacity_profile(left)
    right_capacity = capacity_profile(right)
    if left_capacity.storage_gb is not None and right_capacity.storage_gb is not None and left_capacity.storage_gb != right_capacity.storage_gb:
        return True
    if left_capacity.ram_gb is not None and right_capacity.ram_gb is not None and left_capacity.ram_gb != right_capacity.ram_gb:
        return True
    return False


def _matching_name(name: str) -> str:
    compact = COMPACT_RE.sub(lambda m: f"{m.group(1)}GB {m.group(2)}{m.group(3) or 'GB'}", name or "")
    return normalize_product_name(compact)


def resolve_canonical_product(product_name: str, *, sku_or_ean: str | None = None, minimum_score: float = 0.82) -> CanonicalResolution:
    name = (product_name or "").strip()
    sku = (sku_or_ean or "").strip()
    if sku:
        product = Product.objects.filter(sku_or_ean=sku).first()
        if product:
            return CanonicalResolution(product, 1.0, "sku/ean identique")

    normalized = _matching_name(name)
    if not normalized:
        return CanonicalResolution(None, 0.0, "nom produit vide")

    best_product = None
    best_score = 0.0
    best_reason = "aucun produit canonique compatible"
    for product in Product.objects.all().only("id", "name", "sku_or_ean"):
        if _matching_name(product.name) == normalized:
            return CanonicalResolution(product, 1.0, "nom normalisé identique")
        if has_variant_conflict(name, product.name):
            continue
        result = match_product(_matching_name(name), _matching_name(product.name), threshold=minimum_score)
        if result.is_match and result.score > best_score:
            best_product = product
            best_score = result.score
            best_reason = result.reason

    if best_product is None:
        return CanonicalResolution(None, 0.0, best_reason)
    return CanonicalResolution(best_product, best_score, best_reason)


def get_or_create_canonical_product(product_name: str, *, sku_or_ean: str | None = None) -> tuple[Product, CanonicalResolution]:
    resolution = resolve_canonical_product(product_name, sku_or_ean=sku_or_ean)
    if resolution.product is not None:
        product = resolution.product
        if sku_or_ean and not product.sku_or_ean:
            product.sku_or_ean = sku_or_ean
            product.save(update_fields=["sku_or_ean", "updated_at"])
        return product, resolution

    product = Product.objects.create(name=(product_name or "Produit non identifié").strip(), sku_or_ean=(sku_or_ean or None))
    return product, CanonicalResolution(product, 1.0, "nouveau produit canonique")
