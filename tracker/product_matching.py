import re
import unicodedata
from difflib import SequenceMatcher


ACCESSORY_TOKENS = {
    "case", "cover", "coque", "etui", "étui", "protection", "protector",
    "screen", "verre", "chargeur", "charger", "cable", "câble", "adapter",
    "adaptateur", "support", "holder", "bracelet", "strap", "battery", "batterie",
}


def normalize_product_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _tokens(value: str) -> set[str]:
    return set(normalize_product_name(value).split())


def _variant_tokens(value: str) -> set[str]:
    normalized = normalize_product_name(value)
    variants = set(re.findall(r"\b\d+(?:gb|tb|go|to|mb)\b", normalized))
    variants.update(re.findall(r"\b\d{2,4}\b", normalized))
    return variants


def _is_accessory(value: str) -> bool:
    return bool(_tokens(value) & ACCESSORY_TOKENS)


def product_match_score(query: str, candidate: str) -> float:
    """Return a conservative 0..1 score for two product titles."""
    left = normalize_product_name(query)
    right = normalize_product_name(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    # Do not merge an accessory with the main product.
    if _is_accessory(left) != _is_accessory(right):
        return 0.0

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens
    token_score = len(overlap) / len(union) if union else 0.0
    containment = len(overlap) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    sequence_score = SequenceMatcher(None, left, right).ratio()

    left_variants = _variant_tokens(left)
    right_variants = _variant_tokens(right)
    conflicting_variants = bool(left_variants and right_variants and left_variants.isdisjoint(right_variants))

    score = (0.45 * token_score) + (0.30 * containment) + (0.25 * sequence_score)
    if conflicting_variants:
        score *= 0.55
    return round(max(0.0, min(score, 1.0)), 4)


def is_confident_product_match(query: str, candidate: str, threshold: float = 0.82) -> bool:
    return product_match_score(query, candidate) >= threshold
