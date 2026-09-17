from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import SearchOrScrapeForm
from .market_coverage import coverage_summary, distinct_merchant_count, merchant_key
from .markets import DEFAULT_MARKET_CODE, get_market, normalize_market_code
from .models import ScrapeJob, SearchRun
from .pricing import attach_price_history_stats
from .ranking import attach_offer_quality, offer_sort_key
from .services import process_url_and_save


def _comparison_price(listing):
    return float(listing.normalized_price if listing.normalized_price is not None else listing.price)


def _best_listing_per_merchant(listings):
    """Keep the highest-ranked offer for each normalized merchant identity."""
    best = []
    seen_merchants = set()
    for listing in listings:
        key = merchant_key(listing)
        if key in seen_merchants:
            continue
        seen_merchants.add(key)
        best.append(listing)
    return best


def _decorate_results(listings, query, site="all"):
    if not listings:
        return [], {}
    listings = attach_offer_quality(listings)
    listings = sorted(listings, key=offer_sort_key)
    listings = _best_listing_per_merchant(listings)
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


def _run_state(search_run):
    jobs = ScrapeJob.objects.filter(search_run=search_run)
    active = jobs.filter(status__in=[ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RUNNING, ScrapeJob.STATUS_RETRY])
    successful = jobs.filter(status=ScrapeJob.STATUS_SUCCESS, listing__isnull=False).select_related(
        "listing", "listing__product", "listing__retailer"
    ).order_by("-finished_at")
    listings = []
    seen = set()
    for job in successful:
        if not job.listing_id or job.listing_id in seen:
            continue
        seen.add(job.listing_id)
        listings.append(job.listing)
    total = jobs.count()
    active_count = active.count()
    failed_count = jobs.filter(status=ScrapeJob.STATUS_FAILED).count()
    processed_count = jobs.filter(status__in=[ScrapeJob.STATUS_SUCCESS, ScrapeJob.STATUS_FAILED]).count()
    merchant_count = distinct_merchant_count(listings)
    target = max(1, int(search_run.target_merchants))
    coverage_reached = merchant_count >= target

    if coverage_reached or search_run.status == SearchRun.STATUS_COMPLETED or search_run.completed_at:
        status = "completed"
    elif search_run.status == SearchRun.STATUS_FAILED:
        status = "failed"
    elif search_run.status == SearchRun.STATUS_QUEUED:
        status = "queued"
    elif search_run.status == SearchRun.STATUS_DISCOVERING:
        status = "discovering"
    elif active_count or search_run.status == SearchRun.STATUS_RUNNING:
        status = "running"
    elif total:
        status = "finished"
    else:
        status = "discovering"

    progress = min(100, round((merchant_count / target) * 100)) if target else 0
    return {
        "listings": listings,
        "total": total,
        "active": active_count,
        "failed": failed_count,
        "processed": processed_count,
        "offers": len(listings),
        "merchants": merchant_count,
        "target_merchants": target,
        "coverage_reached": coverage_reached,
        "status": status,
        "progress": progress,
    }


def _async_job_state(query):
    jobs = ScrapeJob.objects.filter(search_run__isnull=True, query__iexact=query)
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


def search_run_status(request, run_id):
    search_run = get_object_or_404(SearchRun, pk=run_id)
    state = _run_state(search_run)
    return JsonResponse({
        "run_id": str(search_run.pk),
        "query": search_run.query,
        "market": search_run.market_code,
        "market_currency": search_run.market_currency,
        "status": state["status"],
        "sources": state["total"],
        "processed": state["processed"],
        "active": state["active"],
        "failed": state["failed"],
        "offers": state["offers"],
        "merchants": state["merchants"],
        "target_merchants": state["target_merchants"],
        "coverage_reached": state["coverage_reached"],
        "progress": state["progress"],
        "completed": state["status"] in {"completed", "finished", "failed"},
        "discovery_error": search_run.discovery_error,
    })


def scrape_view(request):
    listings = []
    discovery_sources = []
    errors = []
    summary = {}
    query = ""
    site = "all"
    market_code = DEFAULT_MARKET_CODE
    async_waiting = False
    async_active_jobs = 0
    search_run = None
    run_state = None

    if request.method == "GET" and request.GET.get("q"):
        query = request.GET.get("q", "").strip()
        site = request.GET.get("site", "all").strip() or "all"
        market_code = normalize_market_code(request.GET.get("market", DEFAULT_MARKET_CODE))
        run_id = request.GET.get("run", "").strip()
        if run_id:
            try:
                search_run = SearchRun.objects.get(pk=run_id, query=query)
                market_code = normalize_market_code(search_run.market_code)
            except (SearchRun.DoesNotExist, ValidationError, ValueError):
                search_run = None
        form = SearchOrScrapeForm(initial={
            "query": query,
            "site": "" if site == "all" else site,
            "market": market_code,
        })
        if search_run:
            run_state = _run_state(search_run)
            listings = run_state["listings"]
            discovery_sources = search_run.discovery_sources or []
            async_active_jobs = run_state["active"]
            async_waiting = run_state["status"] in {"queued", "discovering", "running"}
            if async_waiting:
                errors = [f"Recherche en cours : {run_state['processed']} source(s) analysée(s), {run_state['merchants']}/{run_state['target_merchants']} marchand(s) trouvé(s)."]
            elif run_state["status"] == "failed" and not listings:
                errors = [search_run.discovery_error or "Aucune offre marchande vérifiée n’a été trouvée."]
            elif not listings:
                errors = [f"Aucune offre marchande vérifiée après traitement de {run_state['total']} source(s) ({run_state['failed']} échec(s))."]
        else:
            listings, async_active_jobs, failed_jobs, total_jobs = _async_job_state(query)
            if async_active_jobs:
                async_waiting = True
                errors = [f"Recherche en cours : {async_active_jobs} source(s) encore en traitement."]
            elif not listings and total_jobs:
                errors = [f"Aucune offre marchande vérifiée après traitement de {total_jobs} source(s) ({failed_jobs} échec(s))."]
            elif not listings:
                errors = ["Aucune recherche en cours pour ce produit."]
        if listings:
            listings, summary = _decorate_results(listings, query, site)

        return render(request, "tracker/scrape.html", {
            "form": form,
            "listings": listings,
            "discovery_sources": discovery_sources,
            "errors": errors,
            "summary": summary,
            "async_waiting": async_waiting,
            "async_active_jobs": async_active_jobs,
            "search_run": search_run,
            "run_state": run_state,
        })

    if request.method == "POST":
        form = SearchOrScrapeForm(request.POST)
        if form.is_valid():
            site = form.cleaned_data["site"]
            query = form.cleaned_data["query"].strip()
            market_code = normalize_market_code(form.cleaned_data["market"])
            market = get_market(market_code)
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
                target_merchants = 1 if site != "all" else max(2, int(getattr(settings, "MARKET_COVERAGE_TARGET", 3)))
                search_run = SearchRun.objects.create(
                    query=query,
                    site_filter=site,
                    target_merchants=target_merchants,
                    model_name=model_name or "",
                    market_code=market.code,
                    market_currency=market.currency,
                    status=SearchRun.STATUS_QUEUED,
                )
                params = {"q": query, "run": str(search_run.pk), "market": market.code}
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
        "search_run": search_run,
        "run_state": run_state,
    })
