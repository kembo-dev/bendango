import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


ACCESSORY_TOKENS = {
    "case", "cover", "coque", "etui", "étui", "protection", "protector",
    "screen", "verre", "chargeur", "charger", "cable", "câble", "adapter",
    "adaptateur", "support", "holder", "bracelet", "strap", "battery", "batterie",
    "ecouteur", "ecouteurs", "earbuds", "headset", "vitre", "film",
}

STORAGE_PATTERN = re.compile(r"\b(\d+)\s*(gb|go|tb|to|mb)\b", re.IGNORECASE)
RAM_PATTERN = re.compile(r"\b(\d+)\s*(?:gb|go)\s*(?:ram)?\b", re.IGNORECASE)


@dataclass(frozen=True)
class ProductMatchResult:
    is_match: bool
    score: float
    reason: str


def normalize_product_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.lower()
    value = re.sub(r"\b(pro|max|plus|ultra)\s+(max|plus|ultra)\b", r"\1 \2", value)

    # Canonicalize capacities before punctuation/whitespace cleanup so merchant
    # titles such as "128 GB", "128GB", "128 Go" and "128Go" produce the
    # same token. French Go/To are normalized to GB/TB for cross-shop matching.
    value = re.sub(r"\b(\d+)\s*(gb|go|tb|to|mb)\b", _normalize_capacity_match, value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _normalize_capacity_match(match: re.Match) -> str:
    amount = match.group(1)
    unit = match.group(2).lower()
    unit = {"go": "gb", "to": "tb"}.get(unit, unit)
    return f"{amount}{unit}"


def _tokens(value: str) -> set[str]:
    return set(normalize_product_name(value).split())


def _capacity_tokens(value: str) -> set[str]:
    normalized = normalize_product_name(value)
    return {f"{amount}{unit}" for amount, unit in STORAGE_PATTERN.findall(normalized)}


def _model_number_tokens(value: str) -> set[str]:
    normalized = normalize_product_name(value)
    return set(re.findall(r"\b[a-z]{0,3}\d{1,4}[a-z]{0,3}\b", normalized))


def _is_accessory(value: str) -> bool:
    return bool(_tokens(value) & ACCESSORY_TOKENS)


def _variant_conflict(query: str, candidate: str) -> str | None:
    query_capacities = _capacity_tokens(query)
    candidate_capacities = _capacity_tokens(candidate)
    if query_capacities and candidate_capacities and query_capacities.isdisjoint(candidate_capacities):
        return "capacité différente"

    query_models = _model_number_tokens(query)
    candidate_models = _model_number_tokens(candidate)
    if query_models and candidate_models and query_models.isdisjoint(candidate_models):
        return "référence ou modèle différent"

    return None


def product_match_score(query: str, candidate: str) -> float:
    """Return a conservative similarity score from 0 to 1."""
    left = normalize_product_name(query)
    right = normalize_product_name(candidate)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0

    if _is_accessory(left) != _is_accessory(right):
        return 0.0

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = left_tokens & right_tokens
    union = left_tokens | right_tokens

    token_score = len(overlap) / len(union) if union else 0.0
    containment = len(overlap) / min(len(left_tokens), len(right_tokens)) if left_tokens and right_tokens else 0.0
    sequence_score = SequenceMatcher(None, left, right).ratio()

    score = (0.45 * token_score) + (0.35 * containment) + (0.20 * sequence_score)

    if _variant_conflict(left, right):
        score *= 0.45

    return round(max(0.0, min(score, 1.0)), 4)


def match_product(query: str, candidate: str, threshold: float = 0.72) -> ProductMatchResult:
    """Return a structured product match result with a human-readable reason."""
    left = normalize_product_name(query)
    right = normalize_product_name(candidate)

    if not left or not right:
        return ProductMatchResult(False, 0.0, "requête ou nom produit vide")

    if _is_accessory(left) != _is_accessory(right):
        return ProductMatchResult(False, 0.0, "accessoire détecté à la place du produit principal")

    conflict = _variant_conflict(left, right)
    score = product_match_score(left, right)
    if conflict:
        return ProductMatchResult(False, score, conflict)

    if left in right or right in left:
        return ProductMatchResult(True, max(score, 0.9), "nom contenu dans l'autre intitulé")

    if score >= threshold:
        return ProductMatchResult(True, score, "similarité suffisante")

    return ProductMatchResult(False, score, "similarité insuffisante")


def is_confident_product_match(query: str, candidate: str, threshold: float = 0.72) -> bool:
    return match_product(query, candidate, threshold=threshold).is_match
