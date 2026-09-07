from django.core.exceptions import ValidationError
from django.shortcuts import render
from .forms import SearchOrScrapeForm
from .services import process_url_and_save, search_and_scrape_product


def _comparison_price(item):
    return float(item.normalized_price if item.normalized_price is not None else item.price)


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
            listings = sorted(listings, key=lambda item: (0 if item.in_stock else 1, _comparison_price(item)))
            best_listing = listings[0]
            comparable_prices = [_comparison_price(item) for item in listings]
            average_price = sum(comparable_prices) / len(comparable_prices)
            best_price = _comparison_price(best_listing)
            savings = average_price - best_price
            summary = {
                "best_listing": best_listing,
                "average_price": average_price,
                "savings": savings,
                "savings_percent": (savings / average_price * 100) if average_price else 0,
                "currency": best_listing.normalized_currency,
                "offer_count": len(listings),
                "top_offers": listings[:3],
            }
    else:
        form = SearchOrScrapeForm()

    return render(request, "tracker/scrape.html", {"form": form, "listings": listings, "errors": errors, "summary": summary})
