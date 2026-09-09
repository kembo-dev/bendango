from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import render

from .adaptive_engine import search_and_scrape_product
from .discovery_sources import discover_social_sources
from .forms import SearchOrScrapeForm
from .market_coverage import coverage_summary
from .pricing import attach_price_history_stats
from .ranking import attach_offer_quality, offer_sort_key
from .services import process_url_and_save


def _comparison_price(listing):
    return float(listing.normalized_price if listing.normalized_price is not None else listing.price)


def scrape_view(request):
    listings = []
    discovery_sources = []
    errors = []
    summary = {}

    if request.method == "POST":
        form = SearchOrScrapeForm(request.POST)
        if form.is_valid():
            site = form.cleaned_data["site"]
            query = form.cleaned_data["query"].strip()
            model_name = form.cleaned_data["model_name"]
            if site is not None:
                site = site.strip()
            if not site:
                site = "all"

            if query.startswith("http://") or query.startswith("https://"):
                try:
                    listing, error = process_url_and_save(query, model_name)
                except ValidationError:
                    errors.append("Cette page est déjà enregistrée et a été mise à jour.")
                    listing = None
                    error = None
                if listing:
                    listings.append(listing)
                if error:
                    errors.append(error)
            else:
                listings, errors = search_and_scrape_product(product_query=query, site_filter=site, model_name=model_name)
                discovery_sources = discover_social_sources(query)

        if listings:
            listings = attach_offer_quality(listings)
            listings = sorted(listings, key=offer_sort_key)
            listings = attach_price_history_stats(listings)
            recommended_listing = listings[0]
            in_stock_listings = [item for item in listings if item.in_stock]
            cheapest_listing = min(in_stock_listings or listings, key=_comparison_price)
            normalized_prices = [_comparison_price(item) for item in listings]
            average_price = sum(normalized_prices) / len(normalized_prices)
            recommended_price = _comparison_price(recommended_listing)
            savings = average_price - recommended_price
            savings_percent = (savings / average_price * 100) if average_price else 0
            target_merchants = 1 if query.startswith(("http://", "https://")) or site != "all" else int(getattr(settings, "MARKET_COVERAGE_TARGET", 3))
            summary = {
                "recommended_listing": recommended_listing,
                "cheapest_listing": cheapest_listing,
                "same_recommended_and_cheapest": recommended_listing.pk == cheapest_listing.pk,
                "average_price": average_price,
                "savings": savings,
                "savings_percent": savings_percent,
                "currency": recommended_listing.normalized_currency or "USD",
                "offer_count": len(listings),
                "top_offers": listings[:3],
                "coverage": coverage_summary(listings, target_merchants),
            }
    else:
        form = SearchOrScrapeForm()

    return render(request, "tracker/scrape.html", {
        "form": form,
        "listings": listings,
        "discovery_sources": discovery_sources,
        "errors": errors,
        "summary": summary,
    })
