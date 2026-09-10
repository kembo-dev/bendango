from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render

from .adaptive_engine import search_and_scrape_product
from .discovery_sources import discover_social_sources
from .forms import SearchOrScrapeForm
from .market_coverage import coverage_summary
from .models import ScrapeJob
from .pricing import attach_price_history_stats
from .ranking import attach_offer_quality, offer_sort_key
from .services import process_url_and_save


def _comparison_price(listing):
    return float(listing.normalized_price if listing.normalized_price is not None else listing.price)


def _decorate_results(listings, query, site="all"):
    if not listings:
        return [], {}
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
    return listings, summary


def _async_job_state(query):
    jobs = ScrapeJob.objects.filter(query__iexact=query)
    active = jobs.filter(status__in=[ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RUNNING, ScrapeJob.STATUS_RETRY])
    successful = jobs.filter(status=ScrapeJob.STATUS_SUCCESS, listing__isnull=False).select_related("listing", "listing__product", "listing__retailer").order_by("-finished_at")
    listings = []
    seen = set()
    for job in successful:
        if not job.listing_id or job.listing_id in seen:
            continue
        seen.add(job.listing_id)
        listings.append(job.listing)
    return listings, active.count(), jobs.filter(status=ScrapeJob.STATUS_FAILED).count(), jobs.count()


def scrape_view(request):
    listings = []
    discovery_sources = []
    errors = []
    summary = {}
    query = ""
    site = "all"
    async_waiting = False
    async_active_jobs = 0

    # Async result page: /?q=<product>. This lets the browser leave the original
    # POST and safely refresh while workers complete queued jobs.
    if request.method == "GET" and request.GET.get("q"):
        query = request.GET.get("q", "").strip()
        site = request.GET.get("site", "all").strip() or "all"
        form = SearchOrScrapeForm(initial={"query": query, "site": "" if site == "all" else site})
        listings, async_active_jobs, failed_jobs, total_jobs = _async_job_state(query)
        if listings:
            listings, summary = _decorate_results(listings, query, site)
        if async_active_jobs:
            async_waiting = True
            errors = [f"Recherche en cours : {async_active_jobs} source(s) encore en traitement. Les offres apparaîtront automatiquement."]
        elif not listings and total_jobs:
            errors = [f"Aucune offre marchande vérifiée après traitement de {total_jobs} source(s) ({failed_jobs} échec(s))."]
        elif not listings:
            errors = ["Aucune recherche en cours pour ce produit."]

        response = render(request, "tracker/scrape.html", {
            "form": form,
            "listings": listings,
            "discovery_sources": discovery_sources,
            "errors": errors,
            "summary": summary,
            "async_waiting": async_waiting,
            "async_active_jobs": async_active_jobs,
        })
        if async_waiting:
            response["Refresh"] = "2"
        return response

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

                # In queue mode, leave the POST immediately and move to an idempotent
                # GET that can auto-refresh as workers finish jobs.
                queue_message = any("arrière-plan" in error or "file de collecte" in error for error in errors)
                if not listings and queue_message:
                    params = {"q": query}
                    if site != "all":
                        params["site"] = site
                    return redirect(f"/?{urlencode(params)}")

        if listings:
            listings, summary = _decorate_results(listings, query, site)
    else:
        form = SearchOrScrapeForm()

    return render(request, "tracker/scrape.html", {
        "form": form,
        "listings": listings,
        "discovery_sources": discovery_sources,
        "errors": errors,
        "summary": summary,
        "async_waiting": async_waiting,
        "async_active_jobs": async_active_jobs,
    })
