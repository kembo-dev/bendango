from __future__ import annotations

from decimal import Decimal

from tracker.models import PriceListing


def price_history_stats(listing: PriceListing) -> dict:
    """Build normalized price statistics for one merchant offer."""
    history = list(listing.history.order_by("recorded_at"))
    current = listing.normalized_price
    if current is None:
        current = listing.price

    values = [
        item.normalized_price if item.normalized_price is not None else item.price
        for item in history
    ]
    if not values:
        values = [current]

    previous = values[-2] if len(values) >= 2 else None
    change = (current - previous) if previous is not None else Decimal("0")
    change_percent = (
        (change / previous * Decimal("100"))
        if previous not in (None, Decimal("0"))
        else Decimal("0")
    )

    lowest = min(values)
    highest = max(values)
    lowest_record = None
    for item in history:
        value = item.normalized_price if item.normalized_price is not None else item.price
        if value == lowest:
            lowest_record = item
            break

    return {
        "previous_price": previous,
        "change": change,
        "change_percent": change_percent,
        "lowest_price": lowest,
        "highest_price": highest,
        "lowest_at": lowest_record.recorded_at if lowest_record else None,
        "is_price_drop": previous is not None and current < previous,
        "history_count": len(history),
        "currency": listing.normalized_currency or "USD",
    }


def attach_price_history_stats(listings: list[PriceListing]) -> list[PriceListing]:
    for listing in listings:
        listing.price_stats = price_history_stats(listing)
    return listings
