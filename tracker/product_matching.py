import re
import unicodedata
from dataclasses import dataclass


ACCESSORY_TOKENS = {
    "case", "coque", "cover", "housse", "screen", "protector", "protection",
    "verre", "tempered", "chargeur", "charger", "cable", "câble", "adapter",
    "adaptateur", "earbuds", "ecouteurs", "écouteurs", "support", "holder",
}

CAPACITY_PATTERN = re.compile(r"\b(\d{2,4})\s*(gb|go|tb|to)\b", re.IGNORECASE)


@dataclass(frozen=True)
class MatchResult:
    score: float
    is_match: bool
    reason: str


def normalize_product_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("-", " ").replace("_", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _capacity_tokens(value: str) -> set[str]:
    normalized = normalize_product_text(value)
    return {f"{amount}{unit}" for amount, unit in CAPACITY_PATTERN.findall(normalized)}


def product_match_score(product_name: str, query: str | None) -> MatchResult:
    if not query:
        return MatchResult(1.0, True, "no query constraint")

    normalized_query = normalize_product_text(query)
    normalized_name = normalize_product_text(product_name)
    if not normalized_query or not normalized_name:
        return MatchResult(0.0, False, "empty normalized text")

    query_tokens = set(normalized_query.split())
    name_tokens = set(normalized_name.split())

    query_accessories = query_tokens & ACCESSORY_TOKENS
    name_accessories = name_tokens & ACCESSORY_TOKENS
    if name_accessories and not query_accessories:
        return MatchResult(0.0, False, "result looks like an accessory")

    query_capacities = _capacity_tokens(query)
    name_capacities = _capacity_tokens(product_name)
    if query_capacities and name_capacities and query_capacities.isdisjoint(name_capacities):
        return MatchResult(0.0, False, "storage/capacity mismatch")

    overlap = query_tokens & name_tokens
    recall = len(overlap) / max(len(query_tokens), 1)
    precision = len(overlap) / max(len(name_tokens), 1)
    score = (0.75 * recall) + (0.25 * precision)

    if normalized_query in normalized_name:
        score = max(score, 0.92)

    numeric_query = {token for token in query_tokens if any(ch.isdigit() for ch in token)}
    numeric_name = {token for token in name_tokens if any(ch.isdigit() for ch in token)}
    if numeric_query and not numeric_query.issubset(numeric_name):
        score *= 0.55

    threshold = 0.68
    return MatchResult(round(score, 4), score >= threshold, "token similarity")
