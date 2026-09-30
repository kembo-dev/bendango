from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BusinessAccountRequestForm, BusinessProfileForm, ProCatalogProductForm, SearchOrScrapeForm, SignUpForm
from .market_coverage import coverage_summary, distinct_merchant_count, merchant_key
from .markets import DEFAULT_MARKET_CODE, get_market, normalize_market_code
from .models import BusinessAccountRequest, BusinessProfile, PriceListing, Product, ScrapeJob, SearchRun
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
    elif active_count:
        status = "running"
    elif search_run.discovery_finished_at and total:
        # Discovery is over and every scrape job is terminal. A run with partial
        # coverage must stop polling instead of remaining "running" forever.
        status = "finished"
    elif search_run.status == SearchRun.STATUS_RUNNING:
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


def _recent_search_runs(limit=8, user=None):
    queryset = SearchRun.objects.all()
    if user is not None and getattr(user, "is_authenticated", False):
        queryset = queryset.filter(user=user)
    else:
        queryset = queryset.none()
    return (
        queryset.annotate(
            job_count=Count("jobs", distinct=True),
            offer_count=Count(
                "jobs",
                filter=Q(jobs__status=ScrapeJob.STATUS_SUCCESS, jobs__listing__isnull=False),
                distinct=True,
            ),
        )
        .order_by("-created_at")[:max(1, int(limit))]
    )


@login_required
def search_history(request):
    product_query = (request.GET.get("q") or "").strip()
    searches = SearchRun.objects.filter(user=request.user).annotate(
        job_count=Count("jobs", distinct=True),
        offer_count=Count(
            "jobs",
            filter=Q(jobs__status=ScrapeJob.STATUS_SUCCESS, jobs__listing__isnull=False),
            distinct=True,
        ),
    )
    if product_query:
        searches = searches.filter(query__icontains=product_query)
    searches = searches.order_by("-created_at")[:50]
    return render(request, "tracker/search_history.html", {
        "searches": searches,
        "product_query": product_query,
    })


@login_required
def search_run_detail(request, run_id):
    search_run = get_object_or_404(SearchRun, pk=run_id, user=request.user)
    run_state = _run_state(search_run)
    listings = run_state["listings"]
    summary = {}
    if listings:
        listings, summary = _decorate_results(
            listings,
            search_run.query,
            search_run.site_filter,
        )
    jobs = (
        search_run.jobs.select_related("listing", "listing__product", "listing__retailer")
        .order_by("-created_at")
    )
    return render(request, "tracker/search_run_detail.html", {
        "search_run": search_run,
        "run_state": run_state,
        "listings": listings,
        "summary": summary,
        "discovery_sources": search_run.discovery_sources or [],
        "jobs": jobs,
    })


def signup(request):
    if request.user.is_authenticated:
        return redirect("scrape_view")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Votre compte Bendango a été créé.")
            return redirect("scrape_view")
    else:
        form = SignUpForm()
    return render(request, "tracker/signup.html", {"form": form})


@login_required
def request_business_account(request):
    existing = BusinessAccountRequest.objects.filter(user=request.user).order_by("-created_at").first()
    blocking_request = BusinessAccountRequest.objects.filter(
        user=request.user,
        status__in=[
            BusinessAccountRequest.STATUS_PENDING,
            BusinessAccountRequest.STATUS_APPROVED,
        ],
    ).order_by("-created_at").first()
    if request.method == "POST":
        form = BusinessAccountRequestForm(request.POST)
        if blocking_request:
            messages.info(
                request,
                "Vous avez déjà une demande Pro en attente ou approuvée.",
            )
            return redirect("business_account_request")
        if form.is_valid():
            BusinessAccountRequest.objects.create(
                user=request.user,
                business_name=form.cleaned_data["business_name"],
                business_type=form.cleaned_data["business_type"],
                website=form.cleaned_data["website"],
                phone=form.cleaned_data["phone"],
                description=form.cleaned_data["description"],
            )
            messages.success(
                request,
                "Votre demande de compte Pro a été envoyée. Elle sera examinée par l'équipe Bendango.",
            )
            return redirect("business_account_request")
    else:
        form = BusinessAccountRequestForm()
    return render(request, "tracker/business_account_request.html", {
        "form": form,
        "existing_request": existing,
        "blocking_request": blocking_request,
    })


def _verified_business_profile(request):
    profile = BusinessProfile.objects.filter(
        user=request.user,
        is_verified=True,
    ).first()
    if profile is None:
        approved = BusinessAccountRequest.objects.filter(
            user=request.user,
            status=BusinessAccountRequest.STATUS_APPROVED,
        ).order_by("-reviewed_at", "-created_at").first()
        if approved:
            profile = approved.activate_profile()
    return profile


@login_required
def pro_dashboard(request):
    profile = _verified_business_profile(request)
    if profile is None:
        messages.info(
            request,
            "Votre espace Pro sera disponible après approbation de votre demande.",
        )
        return redirect("business_account_request")

    if request.method == "POST":
        form = BusinessProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Votre profil professionnel a été mis à jour.")
            return redirect("pro_dashboard")
    else:
        form = BusinessProfileForm(instance=profile)

    recent_searches = SearchRun.objects.filter(user=request.user).order_by("-created_at")[:5]
    return render(request, "tracker/pro_dashboard.html", {
        "profile": profile,
        "form": form,
        "recent_searches": recent_searches,
        "search_count": SearchRun.objects.filter(user=request.user).count(),
        "product_count": (
            PriceListing.objects.filter(retailer=profile.retailer).count()
            if profile.retailer_id
            else 0
        ),
    })


@login_required
def pro_products(request):
    profile = _verified_business_profile(request)
    if profile is None:
        messages.info(request, "Votre espace Pro doit être approuvé avant de gérer un catalogue.")
        return redirect("business_account_request")
    retailer = profile.ensure_retailer()
    listings = (
        PriceListing.objects.filter(retailer=retailer)
        .select_related("product")
        .order_by("-scraped_at")
    )
    return render(request, "tracker/pro_products.html", {
        "profile": profile,
        "retailer": retailer,
        "listings": listings,
    })


@login_required
def pro_product_create(request):
    profile = _verified_business_profile(request)
    if profile is None:
        messages.info(request, "Votre espace Pro doit être approuvé avant d'ajouter des produits.")
        return redirect("business_account_request")
    retailer = profile.ensure_retailer()
    if request.method == "POST":
        form = ProCatalogProductForm(request.POST)
        if form.is_valid():
            product = Product.objects.create(
                name=form.cleaned_data["name"],
                brand=form.cleaned_data["brand"],
                model=form.cleaned_data["model"],
                sku_or_ean=form.cleaned_data["sku_or_ean"] or None,
                category=form.cleaned_data["category"],
                image_url=form.cleaned_data["image_url"],
            )
            PriceListing.objects.create(
                product=product,
                retailer=retailer,
                url=form.cleaned_data["sale_url"],
                price=form.cleaned_data["price"],
                currency=form.cleaned_data["currency"],
                confidence_score=1,
                match_score=1,
                extraction_source="unknown",
                in_stock=form.cleaned_data["in_stock"],
                is_active=True,
            )
            messages.success(request, "Le produit a été ajouté à votre catalogue Pro.")
            return redirect("pro_products")
    else:
        form = ProCatalogProductForm()
    return render(request, "tracker/pro_product_form.html", {
        "profile": profile,
        "form": form,
        "page_title": "Ajouter un produit",
        "submit_label": "Ajouter au catalogue",
    })


@login_required
def pro_product_edit(request, listing_id):
    profile = _verified_business_profile(request)
    if profile is None:
        messages.info(request, "Votre espace Pro doit être approuvé avant de modifier un produit.")
        return redirect("business_account_request")
    retailer = profile.ensure_retailer()
    listing = get_object_or_404(
        PriceListing.objects.select_related("product"),
        pk=listing_id,
        retailer=retailer,
    )
    product = listing.product
    initial = {
        "name": product.name,
        "brand": product.brand,
        "model": product.model,
        "sku_or_ean": product.sku_or_ean or "",
        "category": product.category,
        "image_url": product.image_url,
        "price": listing.price,
        "currency": listing.currency,
        "in_stock": listing.in_stock,
        "sale_url": listing.url,
    }
    if request.method == "POST":
        form = ProCatalogProductForm(request.POST)
        if form.is_valid():
            if product.listings.exclude(retailer=retailer).exists():
                product = Product.objects.create(
                    name=form.cleaned_data["name"],
                    brand=form.cleaned_data["brand"],
                    model=form.cleaned_data["model"],
                    sku_or_ean=form.cleaned_data["sku_or_ean"] or None,
                    category=form.cleaned_data["category"],
                    image_url=form.cleaned_data["image_url"],
                )
                listing.product = product
            else:
                product.name = form.cleaned_data["name"]
                product.brand = form.cleaned_data["brand"]
                product.model = form.cleaned_data["model"]
                product.sku_or_ean = form.cleaned_data["sku_or_ean"] or None
                product.category = form.cleaned_data["category"]
                product.image_url = form.cleaned_data["image_url"]
                product.save()
            listing.url = form.cleaned_data["sale_url"]
            listing.price = form.cleaned_data["price"]
            listing.currency = form.cleaned_data["currency"]
            listing.in_stock = form.cleaned_data["in_stock"]
            listing.is_active = True
            listing.confidence_score = 1
            listing.match_score = 1
            listing.save()
            messages.success(request, "Le produit a été mis à jour.")
            return redirect("pro_products")
    else:
        form = ProCatalogProductForm(initial=initial)
    return render(request, "tracker/pro_product_form.html", {
        "profile": profile,
        "form": form,
        "listing": listing,
        "page_title": "Modifier le produit",
        "submit_label": "Enregistrer les modifications",
    })


@login_required
def pro_product_toggle(request, listing_id):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect("business_account_request")
    retailer = profile.ensure_retailer()
    listing = get_object_or_404(PriceListing, pk=listing_id, retailer=retailer)
    if request.method == "POST":
        listing.is_active = not listing.is_active
        listing.save(update_fields=["is_active"])
        messages.success(
            request,
            "Produit activé." if listing.is_active else "Produit désactivé.",
        )
    return redirect("pro_products")


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


def _accessible_search_run(request, run_id):
    queryset = SearchRun.objects.filter(pk=run_id)
    if request.user.is_authenticated:
        queryset = queryset.filter(Q(user=request.user) | Q(user__isnull=True))
    else:
        queryset = queryset.filter(user__isnull=True)
    return get_object_or_404(queryset)


def search_run_status(request, run_id):
    search_run = _accessible_search_run(request, run_id)
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
    anonymous_search_used = (
        not request.user.is_authenticated
        and bool(request.session.get("anonymous_search_used"))
    )
    recent_searches = _recent_search_runs(limit=8, user=request.user)
    business_profile = (
        BusinessProfile.objects.filter(user=request.user, is_verified=True).first()
        if request.user.is_authenticated
        else None
    )
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
                search_run = _accessible_search_run(request, run_id)
                if search_run.query != query:
                    search_run = None
                elif search_run is not None:
                    market_code = normalize_market_code(search_run.market_code)
            except (ValidationError, ValueError):
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
                if discovery_sources:
                    errors = [
                        "Aucune offre marchande vérifiée, mais Bendango a trouvé des sources utiles sur d’autres plateformes."
                    ]
                else:
                    errors = [search_run.discovery_error or "Aucune offre marchande vérifiée n’a été trouvée."]
            elif not listings:
                if discovery_sources:
                    errors = [
                        f"Aucune offre marchande vérifiée après traitement de {run_state['total']} source(s), mais {len(discovery_sources)} source(s) utile(s) ont été trouvée(s) sur d’autres plateformes."
                    ]
                else:
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
            "recent_searches": recent_searches,
            "business_profile": business_profile,
            "anonymous_search_used": anonymous_search_used,
        })

    if request.method == "POST":
        if anonymous_search_used:
            return redirect("signup")
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
                if not request.user.is_authenticated:
                    request.session["anonymous_search_used"] = True
            else:
                target_merchants = 1 if site != "all" else max(2, int(getattr(settings, "MARKET_COVERAGE_TARGET", 3)))
                search_run = SearchRun.objects.create(
                    user=request.user if request.user.is_authenticated else None,
                    query=query,
                    site_filter=site,
                    target_merchants=target_merchants,
                    model_name=model_name or "",
                    market_code=market.code,
                    market_currency=market.currency,
                    status=SearchRun.STATUS_QUEUED,
                )
                if not request.user.is_authenticated:
                    request.session["anonymous_search_used"] = True
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
        "recent_searches": recent_searches,
        "business_profile": business_profile,
        "anonymous_search_used": anonymous_search_used,
    })
