from decimal import Decimal, InvalidOperation

from django.conf import settings


DEFAULT_USD_RATES = {
    "USD": Decimal("1"),
    "CDF": Decimal("2850"),
    "EUR": Decimal("0.86"),
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


def normalize_to_usd(amount, currency: str):
    """Convert an amount to USD using configurable 'units per USD' rates."""
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None
    code = (currency or "").strip().upper()
    rate = get_usd_rates().get(code)
    if value <= 0 or not rate:
        return None
    return (value / rate).quantize(Decimal("0.01"))


def normalize_currency(amount, currency: str):
    """Backward-compatible alias used by older service code.

    Bendango's canonical comparison currency is USD, so this helper delegates
    to normalize_to_usd(). New code should prefer normalize_to_usd directly.
    """
    return normalize_to_usd(amount, currency)
