from django.core.exceptions import ValidationError
from django.shortcuts import render
from .forms import SearchOrScrapeForm
from .services import process_url_and_save, search_and_scrape_product


def _comparison_price(item):
    return float(item.normalized_price if item.normalized_price is not None else item.price)


def _decorate_listing_for_display(listing):
    history = list(listing.history.order_by('-captured_at')[:2])
    listing.history_count = listing.history.count()
    listing.previous_observation = history[1] if len(history) > 1 else None
    listing.price_change = None
    listing.price_change_percent = None
    if listing.previous_observation and listing.previous_observation.normalized_price:
        previous = float(listing.previous_observation.normalized_price)
        current = _comparison_price(listing)
        if previous:
            listing.price_change = current - previous
            listing.price_change_percent = ((current - previous) / previous) * 100
    listing.confidence_percent = round(float(listing.confidence_score or 0) * 100)
    return listing


def scrape_view(request):
    listings = []
    errors = []
    summary = {}

    if request.method == "POST":
        form = SearchOrScrapeForm(request.POST)
        if form.is_valid():
            site = (form.cleaned_data["site"] or "all").strip() or "all"
            query = form.cleaned_data["query"].strip()
            model_name = form.cleaned_data["model_name"]
            if query.startswith(("http://", "https://")):
                try:
                    listing, error = process_url_and_save(query, model_name)
                except ValidationError as exc:
                    listing, error = None, "; ".join(exc.messages)
                if listing:
                    listings.append(listing)
                if error:
                    errors.append(error)
            else:
                listings, errors = search_and_scrape_product(query, site, model_name)

        if listings:
            listings = [_decorate_listing_for_display(item) for item in listings]
            listings = sorted(listings, key=lambda item: (0 if item.in_stock else 1, _comparison_price(item)))
            best_listing = listings[0]
            comparable_prices = [_comparison_price(item) for item in listings]
            average_price = sum(comparable_prices) / len(comparable_prices)
            best_price = _comparison_price(best_listing)
            savings = average_price - best_price
            summary = {
                "best_listing": best_listing,
                "best_price_normalized": best_price,
                "average_price": average_price,
                "savings": savings,
                "savings_percent": (savings / average_price * 100) if average_price else 0,
                "currency": best_listing.normalized_currency,
                "offer_count": len(listings),
                "top_offers": listings[:3],
                "in_stock_count": sum(1 for item in listings if item.in_stock),
            }
    else:
        form = SearchOrScrapeForm()

    return render(request, "tracker/scrape.html", {"form": form, "listings": listings, "errors": errors, "summary": summary})
