from decimal import Decimal, InvalidOperation

from django.conf import settings


DEFAULT_USD_RATES = {
    "USD": Decimal("1"),
    "CDF": Decimal("2850"),
    "EUR": Decimal("0.86"),
}

CURRENCY_ALIASES = {
    "US$": "USD",
    "$": "USD",
    "USD": "USD",
    "FC": "CDF",
    "FCFA": "CDF",
    "CDF": "CDF",
    "FRANC CONGOLAIS": "CDF",
    "FRANCS CONGOLAIS": "CDF",
    "€": "EUR",
    "EUR": "EUR",
    "EURO": "EUR",
    "EUROS": "EUR",
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


def normalize_currency_code(currency: str | None) -> str:
    """Return a canonical ISO-like currency code used by Bendango."""
    raw = (currency or "").strip().upper()
    if not raw:
        return "USD"
    return CURRENCY_ALIASES.get(raw, raw)


def normalize_to_usd(amount, currency: str):
    """Convert an amount to USD using configurable 'units per USD' rates."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None

    code = normalize_currency_code(currency)
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
