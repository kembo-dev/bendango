from decimal import Decimal, InvalidOperation

from django.conf import settings


SUPPORTED_CURRENCIES = {"CDF", "USD", "EUR"}
ALIASES = {
    "$": "USD", "US$": "USD", "USD": "USD",
    "FC": "CDF", "FCFA": "CDF", "CDF": "CDF",
    "€": "EUR", "EUR": "EUR",
}


def normalize_currency(value: str | None) -> str | None:
    raw = (value or "").strip().upper()
    normalized = ALIASES.get(raw, raw)
    return normalized if normalized in SUPPORTED_CURRENCIES else None


def get_fx_rates() -> dict[str, Decimal]:
    configured = getattr(settings, "BENDANGO_FX_RATES", {}) or {}
    defaults = {"USD": Decimal("1"), "CDF": Decimal("2800"), "EUR": Decimal("0.86")}
    rates = {}
    for currency, default in defaults.items():
        try:
            rates[currency] = Decimal(str(configured.get(currency, default)))
        except (InvalidOperation, TypeError, ValueError):
            rates[currency] = default
    return rates


def convert_price(amount, source_currency: str, target_currency: str = "USD") -> Decimal | None:
    source = normalize_currency(source_currency)
    target = normalize_currency(target_currency)
    if source is None or target is None:
        return None
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None

    rates = get_fx_rates()
    # Rates are expressed as units of each currency per 1 USD.
    usd_value = value / rates[source]
    return (usd_value * rates[target]).quantize(Decimal("0.01"))
