from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    code: str
    label: str
    country: str
    currency: str
    tlds: tuple[str, ...]
    hints: tuple[str, ...]
    cities: tuple[str, ...]


MARKETS = {
    "CD": MarketProfile("CD", "🇨🇩 République démocratique du Congo", "RDC", "CDF", (".cd",), ("rdc", "drc", "congo"), ("kinshasa", "goma", "lubumbashi")),
    "FR": MarketProfile("FR", "🇫🇷 France", "France", "EUR", (".fr",), ("france",), ("paris", "lyon", "marseille")),
    "CI": MarketProfile("CI", "🇨🇮 Côte d’Ivoire", "Côte d’Ivoire", "XOF", (".ci",), ("cote d ivoire", "ivoire"), ("abidjan", "bouake")),
    "SN": MarketProfile("SN", "🇸🇳 Sénégal", "Sénégal", "XOF", (".sn",), ("senegal",), ("dakar", "thies")),
    "MA": MarketProfile("MA", "🇲🇦 Maroc", "Maroc", "MAD", (".ma",), ("maroc", "morocco"), ("casablanca", "rabat", "marrakech")),
    "CA": MarketProfile("CA", "🇨🇦 Canada", "Canada", "CAD", (".ca",), ("canada",), ("montreal", "toronto", "vancouver")),
    "US": MarketProfile("US", "🇺🇸 États-Unis", "United States", "USD", (".us",), ("usa", "united states"), ("new york", "los angeles", "chicago")),
    "BE": MarketProfile("BE", "🇧🇪 Belgique", "Belgique", "EUR", (".be",), ("belgique", "belgium"), ("bruxelles", "brussels", "liege")),
    "CM": MarketProfile("CM", "🇨🇲 Cameroun", "Cameroun", "XAF", (".cm",), ("cameroun", "cameroon"), ("douala", "yaounde")),
    "KE": MarketProfile("KE", "🇰🇪 Kenya", "Kenya", "KES", (".ke", ".co.ke"), ("kenya",), ("nairobi", "mombasa")),
    "NG": MarketProfile("NG", "🇳🇬 Nigeria", "Nigeria", "NGN", (".ng", ".com.ng"), ("nigeria",), ("lagos", "abuja")),
    "TZ": MarketProfile("TZ", "🇹🇿 Tanzanie", "Tanzania", "TZS", (".tz", ".co.tz"), ("tanzania",), ("dar es salaam", "arusha")),
}

DEFAULT_MARKET_CODE = "CD"


def normalize_market_code(code: str | None) -> str:
    normalized = (code or "").strip().upper()
    return normalized if normalized in MARKETS else DEFAULT_MARKET_CODE


def get_market(code: str | None) -> MarketProfile:
    return MARKETS[normalize_market_code(code)]


def market_choices() -> list[tuple[str, str]]:
    return [(profile.code, profile.label) for profile in MARKETS.values()]


def market_search_label(code: str | None) -> str:
    profile = get_market(code)
    if profile.cities:
        return f"{profile.country} {profile.cities[0]}"
    return profile.country
