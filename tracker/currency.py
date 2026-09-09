from decimal import Decimal, InvalidOperation

from django.conf import settings


DEFAULT_USD_RATES = {
    "USD": Decimal("1"),
    "CDF": Decimal("2850"),
    "EUR": Decimal("0.86"),
    # CFA francs are pegged to the euro at 655.957 CFA per EUR. With the
    # default EUR rate above (0.86 EUR per USD), that is about 564.12 CFA/USD.
    # Deployments can override both values through BENDANGO_USD_RATES.
    "XOF": Decimal("564.12"),
    "XAF": Decimal("564.12"),
}

CURRENCY_ALIASES = {
    "US$": "USD",
    "$": "USD",
    "USD": "USD",
    "FC": "CDF",
    "CDF": "CDF",
    "FRANC CONGOLAIS": "CDF",
    "FRANCS CONGOLAIS": "CDF",
    "XOF": "XOF",
    "XAF": "XAF",
    "CFA": "XOF",
    "FCFA": "XOF",
    "F CFA": "XOF",
    "FRANC CFA": "XOF",
    "FRANCS CFA": "XOF",
    "€": "EUR",
    "EUR": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
}

WEST_AFRICAN_CFA_HINTS = {
    "senegal", "sénégal", "dakar", "cote d'ivoire", "côte d'ivoire", "abidjan",
    "benin", "bénin", "togo", "burkina", "mali", "niger", "guinee-bissau", "guinée-bissau",
}

CENTRAL_AFRICAN_CFA_HINTS = {
    "cameroun", "cameroon", "yaounde", "yaoundé", "douala", "gabon", "libreville",
    "tchad", "chad", "centrafrique", "republique centrafricaine", "république centrafricaine",
    "guinee equatoriale", "guinée équatoriale", "equatorial guinea", "congo-brazzaville", "brazzaville",
}


def get_usd_rates() -> dict[str, Decimal]:
    configured = getattr(settings, "BENDANGO_USD_RATES", {}) or {}
    rates = dict(DEFAULT_USD_RATES)
    for currency, value in configured.items():
        try:
            rate = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if rate > 0:
            rates[str(currency).upper()] = rate
    return rates


def infer_cfa_currency(context: str | None = None) -> str:
    """Infer XOF vs XAF from page/location context; default generic CFA to XOF."""
    text = (context or "").lower()
    if any(hint in text for hint in CENTRAL_AFRICAN_CFA_HINTS):
        return "XAF"
    if any(hint in text for hint in WEST_AFRICAN_CFA_HINTS):
        return "XOF"
    return "XOF"


def normalize_currency_code(currency: str | None, context: str | None = None) -> str:
    """Return a canonical ISO-like currency code used by Bendango."""
    raw = " ".join((currency or "").strip().upper().split())
    if not raw:
        return "USD"
    if raw in {"CFA", "FCFA", "F CFA", "FRANC CFA", "FRANCS CFA"}:
        return infer_cfa_currency(context)
    return CURRENCY_ALIASES.get(raw, raw)


def normalize_to_usd(amount, currency: str, context: str | None = None):
    """Convert an amount to USD using configurable 'units per USD' rates."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None

    code = normalize_currency_code(currency, context=context)
    rate = get_usd_rates().get(code)
    if value <= 0 or not rate:
        return None
    return (value / rate).quantize(Decimal("0.01"))


def normalize_currency(value, currency: str | None = None):
    """Compatibility helper for both Bendango currency call styles.

    normalize_currency("FC") -> "CDF"
    normalize_currency(2850, "CDF") -> Decimal("1.00")

    New code should prefer normalize_currency_code() for codes and
    normalize_to_usd() for monetary conversion.
    """
    if currency is None:
        return normalize_currency_code(value)
    return normalize_to_usd(value, currency)
