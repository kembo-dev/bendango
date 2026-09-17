from __future__ import annotations

import re
from collections import Counter

from tracker.models import SearchDiagnostic
from tracker.search_diagnostics import classify_search_error


DEFAULT_LOCAL_TERMS = (
    '"{query}" {country} prix acheter',
    '"{query}" {country} prix',
    '{query} {country} boutique en ligne',
)

DEFAULT_GLOBAL_TERMS = (
    '{query} acheter prix',
    '{query} prix',
    '{query} vendeur {country}',
    '{query} magasin {country}',
)

# Broad category-like queries (for example "string femme" or "tournevis")
# tend to surface category/listing pages. Ask the search engine for strong
# product-detail URL shapes first, then broaden only if needed.
BROAD_PRODUCT_DETAIL_TERMS = (
    '"{query}" {country} inurl:product',
    '"{query}" {country} inurl:produit',
    '"{query}" {country} inurl:item',
    '"{query}" inurl:product price',
    '"{query}" inurl:produit prix',
)

BROAD_LOCAL_TERMS = (
    '"{query}" {country} "ajouter au panier"',
    '"{query}" {country} acheter "en stock"',
    '"{query}" {country} acheter prix',
    '"{query}" {country} boutique livraison prix',
)

BROAD_GLOBAL_TERMS = (
    '"{query}" "ajouter au panier"',
    '"{query}" acheter "en stock" prix',
    '"{query}" boutique en ligne prix',
    '"{query}" shop buy price',
)


def _unique(values):
    seen = set()
    output = []
    for value in values:
        value = (value or "").strip()
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output


def is_broad_product_query(query: str) -> bool:
    tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", query or "")
    meaningful = [token for token in tokens if len(token) > 1]
    has_model_signal = any(any(char.isdigit() for char in token) for token in tokens)
    return bool(meaningful) and len(meaningful) <= 2 and not has_model_signal


def recent_failure_profile(query: str, limit: int = 5) -> Counter:
    profile = Counter()
    rows = SearchDiagnostic.objects.filter(query__iexact=query).order_by('-created_at')[:limit]
    for row in rows:
        for reason, count in (row.rejection_reasons or {}).items():
            try:
                profile[reason] += int(count or 0)
            except (TypeError, ValueError):
                continue
    return profile


def build_adaptive_search_terms(query: str, country: str = 'RDC', diagnostics=None):
    """Build search passes for the selected market without fixed merchant preference."""
    profile = Counter(diagnostics or recent_failure_profile(query))
    broad = is_broad_product_query(query)

    terms = []
    if broad:
        terms.extend(template.format(query=query, country=country) for template in BROAD_PRODUCT_DETAIL_TERMS)
        terms.extend(template.format(query=query, country=country) for template in BROAD_LOCAL_TERMS)
    else:
        terms.extend(template.format(query=query, country=country) for template in DEFAULT_LOCAL_TERMS)

    if profile['product_mismatch']:
        if broad:
            terms.extend([
                f'"{query}" {country} inurl:product',
                f'"{query}" {country} inurl:produit',
                f'"{query}" acheter produit prix',
                f'"{query}" "en stock" boutique',
                f'"{query}" product buy price',
            ])
        else:
            terms.extend([
                f'{query} modèle exact prix',
                f'{query} référence acheter',
                f'intitle:"{query}" prix',
            ])

    if profile['no_product_structure'] or profile['extraction_failed'] or profile['invalid_data']:
        terms.extend([
            f'{query} fiche produit prix',
            f'{query} "en stock" prix',
            f'{query} product price buy',
        ])

    if profile['fetch_failed'] or profile['not_found']:
        if broad:
            terms.extend([
                f'"{query}" {country} inurl:product',
                f'"{query}" {country} inurl:produit',
            ])
        terms.extend([
            f'{query} boutique {country}',
            f'{query} revendeur {country}',
            f'{query} shop price',
        ])

    if profile['no_candidates']:
        terms.extend([
            f'{query} {country} prix',
            f'{query} {country} price',
            f'{query} online store',
        ])

    global_templates = BROAD_GLOBAL_TERMS if broad else DEFAULT_GLOBAL_TERMS
    terms.extend(template.format(query=query, country=country) for template in global_templates)
    return _unique(terms)


def build_recovery_terms(query: str, errors, country: str = 'RDC'):
    reasons = Counter(classify_search_error(error) for error in (errors or []))
    return build_adaptive_search_terms(query, country=country, diagnostics=reasons)
