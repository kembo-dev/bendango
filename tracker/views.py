from django.core.exceptions import ValidationError
from django.shortcuts import render
from .forms import SearchOrScrapeForm
from .services import process_url_and_save, search_and_scrape_product


def scrape_view(request):
    listings = []
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
                except ValidationError as exc:
                    errors.append("Cette page est déjà enregistrée et a été mise à jour.")
                    listing = None
                    error = None
                if listing:
                    listings.append(listing)
                if error:
                    errors.append(error)
            else:
                listings, errors = search_and_scrape_product(
                    product_query=query,
                    site_filter=site,
                    model_name=model_name,
                )

        if listings:
            listings = sorted(
                listings,
                key=lambda item: (0 if item.in_stock else 1, float(item.price)),
            )
            best_listing = listings[0]
            average_price = sum(float(item.price) for item in listings) / len(listings)
            savings = average_price - float(best_listing.price)
            savings_percent = (savings / average_price * 100) if average_price else 0
            top_offers = listings[:3]
            summary = {
                "best_listing": best_listing,
                "average_price": average_price,
                "savings": savings,
                "savings_percent": savings_percent,
                "currency": best_listing.currency,
                "offer_count": len(listings),
                "top_offers": top_offers,
            }
    else:
        form = SearchOrScrapeForm()

    return render(
        request,
        "tracker/scrape.html",
        {
            "form": form,
            "listings": listings,
            "errors": errors,
            "summary": summary,
        },
    )