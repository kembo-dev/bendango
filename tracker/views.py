import re
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import BusinessAccountRequestForm, BusinessProfileForm, OfferBoostRequestForm, OfferEditForm, ProCatalogProductForm, QuickOfferForm, SearchOrScrapeForm, SignUpForm
from .market_coverage import coverage_summary, distinct_merchant_count, merchant_key
from .offer_search import find_matching_offers
from .unified_search import build_unified_results
from .markets import DEFAULT_MARKET_CODE, get_market, normalize_market_code
from .models import BusinessAccountRequest, BusinessProfile, Offer, OfferBoostRequest, OfferMedia, PriceListing, Product, ScrapeJob, SearchRun
from .pro_overview import dashboard_context
from .pricing import attach_price_history_stats
from .ranking import attach_offer_quality, offer_sort_key
from .services import LLMRequiredError, LLM_PUBLIC_ERROR, get_llm_config, get_llm_model_reference, process_url_and_save


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


def _public_discovery_feed(request, *, per_page=12):
    offers = list(
        Offer.objects.filter(
            is_public=True,
            is_active=True,
            business__is_public=True,
            business__is_active=True,
        )
        .select_related("business")
        .prefetch_related("media", "boost_requests")
        .order_by("-updated_at")[:120]
    )

    offers.sort(
        key=lambda offer: (
            0 if offer.is_boosted else 1,
            -offer.updated_at.timestamp(),
        )
    )

    recent_runs = list(
        SearchRun.objects.filter(query__gt="")
        .annotate(
            offer_count=Count(
                "jobs",
                filter=Q(
                    jobs__status=ScrapeJob.STATUS_SUCCESS,
                    jobs__listing__isnull=False,
                ),
                distinct=True,
            )
        )
        .order_by("-created_at")[:180]
    )

    # Public discovery shows search topics, never another user's identity or run UUID.
    deduped_runs = []
    seen_queries = set()
    for run in recent_runs:
        key = (run.query.strip().lower(), run.market_code)
        if not run.query.strip() or key in seen_queries:
            continue
        seen_queries.add(key)
        deduped_runs.append(run)
        if len(deduped_runs) >= 120:
            break

    listing_by_run = {}
    run_ids = [run.pk for run in deduped_runs]
    if run_ids:
        jobs = (
            ScrapeJob.objects.filter(
                search_run_id__in=run_ids,
                status=ScrapeJob.STATUS_SUCCESS,
                listing__isnull=False,
            )
            .select_related("listing__product", "listing__retailer")
            .order_by("-finished_at", "-pk")
        )
        for job in jobs:
            listing_by_run.setdefault(job.search_run_id, job.listing)

    offer_items = []
    for offer in offers:
        offer_items.append({
            "kind": "offer",
            "title": offer.title,
            "image_url": offer.display_image_url or "",
            "price": offer.price,
            "currency": offer.currency,
            "price_unit": offer.price_unit,
            "provider": offer.business.business_name,
            "city": offer.city or offer.business.city or "",
            "market_code": offer.market_code,
            "badge": "Publié sur Bendango",
            "promoted": bool(offer.offer_type == Offer.TYPE_PRODUCT and offer.is_boosted),
            "url": f"/offer/{offer.slug}/",
            "created_at": offer.updated_at,
        })

    search_items = []
    for run in deduped_runs:
        listing = listing_by_run.get(run.pk)
        params = {"q": run.query, "market": run.market_code}
        search_items.append({
            "kind": "search",
            "title": run.query,
            "image_url": (
                listing.product.image_url
                if listing and listing.product and listing.product.image_url
                else ""
            ),
            "price": listing.price if listing else None,
            "currency": listing.currency if listing else run.market_currency,
            "price_unit": "",
            "provider": "Recherche Bendango",
            "city": "",
            "market_code": run.market_code,
            "badge": "Recherché récemment",
            "offer_count": run.offer_count,
            "url": f"/?{urlencode(params)}",
            "created_at": run.created_at,
        })

    # Interleave first-party offers and community searches so both are visible.
    feed = []
    max_len = max(len(offer_items), len(search_items))
    for index in range(max_len):
        if index < len(offer_items):
            feed.append(offer_items[index])
        if index < len(search_items):
            feed.append(search_items[index])

    paginator = Paginator(feed, per_page)
    return paginator.get_page(request.GET.get("page") or 1)


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
    searches = searches.order_by("-created_at")
    paginator = Paginator(searches, 12)
    searches = paginator.get_page(request.GET.get("page") or 1)
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
        is_individual=False,
    ).first()
    if profile is None:
        approved = BusinessAccountRequest.objects.filter(
            user=request.user,
            status=BusinessAccountRequest.STATUS_APPROVED,
        ).order_by("-reviewed_at", "-created_at").first()
        if approved:
            profile = approved.activate_profile()
    return profile


def public_business(request, slug):
    profile = get_object_or_404(
        BusinessProfile.objects.select_related("category", "retailer"),
        slug=slug,
        is_public=True,
        is_active=True,
    )
    offers = list(
        profile.offers.filter(is_public=True, is_active=True)
        .select_related('product', 'price_listing')
        .prefetch_related('media')
        .order_by('-updated_at')
    )
    bridged_listing_ids = {
        offer.price_listing_id for offer in offers if offer.price_listing_id
    }
    listings = []
    if profile.retailer_id:
        listings = list(
            PriceListing.objects.filter(
                retailer=profile.retailer,
                is_active=True,
            )
            .exclude(pk__in=bridged_listing_ids)
            .select_related("product")
            .order_by("-scraped_at")
        )
    whatsapp_digits = re.sub(r"\D+", "", profile.whatsapp or profile.phone or "")
    return render(request, "tracker/public_business.html", {
        "profile": profile,
        "offers": offers,
        "listings": listings,
        "whatsapp_url": f"https://wa.me/{whatsapp_digits}" if whatsapp_digits else "",
    })


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

    return render(request, "tracker/pro_dashboard.html", {
        "profile": profile,
        "form": form,
        "show_profile": request.GET.get("section") == "profile" or request.method == "POST",
        **dashboard_context(profile, request.user),
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


def _sync_offer_product_bridge(offer):
    if offer.offer_type != Offer.TYPE_PRODUCT:
        return offer
    if offer.product_id:
        product = offer.product
        product.name = offer.title
        product.category = offer.category
        product.image_url = offer.primary_image_url
        product.save(update_fields=['name', 'category', 'image_url', 'updated_at'])
    else:
        product = Product.objects.create(
            name=offer.title,
            category=offer.category,
            image_url=offer.primary_image_url,
        )
        offer.product = product
        offer.save(update_fields=['product'])

    if offer.external_url and offer.price is not None:
        retailer = offer.business.ensure_retailer()
        if offer.price_listing_id:
            listing = offer.price_listing
            listing.product = product
            listing.retailer = retailer
            listing.url = offer.external_url
            listing.price = offer.price
            listing.currency = offer.currency
            listing.in_stock = offer.availability == 'available'
            listing.is_active = offer.is_active and offer.is_public
            listing.confidence_score = 1
            listing.match_score = 1
            listing.save()
        else:
            listing = PriceListing.objects.create(
                product=product,
                retailer=retailer,
                url=offer.external_url,
                price=offer.price,
                currency=offer.currency,
                confidence_score=1,
                match_score=1,
                extraction_source='unknown',
                in_stock=offer.availability == 'available',
                is_active=offer.is_active and offer.is_public,
            )
            offer.price_listing = listing
            offer.save(update_fields=['price_listing'])
    elif offer.price_listing_id:
        PriceListing.objects.filter(pk=offer.price_listing_id).update(is_active=False)
    return offer


def _attach_offer_media(offer, uploaded_files):
    uploaded_files = list(uploaded_files or [])
    if not uploaded_files:
        return
    start_position = offer.media.count()
    has_primary = offer.media.filter(is_primary=True).exists()
    for index, uploaded in enumerate(uploaded_files):
        OfferMedia.objects.create(
            offer=offer,
            file=uploaded,
            alt_text=offer.title,
            position=start_position + index,
            is_primary=not has_primary and index == 0,
        )


def public_offer(request, slug):
    offer = get_object_or_404(
        Offer.objects.select_related('business', 'business__category', 'product').prefetch_related('boost_requests'),
        slug=slug,
        is_public=True,
        is_active=True,
        business__is_public=True,
        business__is_active=True,
    )
    media = list(offer.media.all())
    primary_media = next((item for item in media if item.is_primary), media[0] if media else None)
    gallery_images = [
        {'url': item.url, 'thumbnail_url': item.thumbnail_url, 'alt': item.alt_text or offer.title}
        for item in sorted(media, key=lambda item: not item.is_primary)
        if item.url
    ]
    if not gallery_images and offer.primary_image_url:
        gallery_images = [{'url': offer.primary_image_url, 'alt': offer.title}]
    whatsapp_digits = re.sub(r"\D+", "", offer.whatsapp or offer.business.whatsapp or offer.business.phone or "")
    return render(request, 'tracker/public_offer.html', {
        'offer': offer,
        'media': media,
        'primary_media': primary_media,
        'gallery_images': gallery_images,
        'whatsapp_url': f"https://wa.me/{whatsapp_digits}" if whatsapp_digits else '',
    })


@login_required
def pro_offers(request):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    offers = list(
        profile.offers
        .select_related('product', 'price_listing')
        .prefetch_related('media', 'boost_requests')
        .order_by('-updated_at')
    )
    for offer in offers:
        requests = list(offer.boost_requests.all())
        offer.latest_boost_request = requests[0] if requests else None
        offer.active_boost = next((item for item in requests if item.is_active), None)
    return render(request, 'tracker/pro_offers.html', {
        'profile': profile,
        'offers': offers,
    })


@login_required
def pro_offer_boost_request(request, offer_id):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    offer = get_object_or_404(Offer, pk=offer_id, business=profile)
    if offer.offer_type != Offer.TYPE_PRODUCT:
        messages.error(request, "Le boost est disponible uniquement pour les produits.")
        return redirect('pro_offers')

    now = timezone.now()
    existing = OfferBoostRequest.objects.filter(
        offer=offer,
    ).filter(
        Q(status=OfferBoostRequest.STATUS_PENDING)
        | Q(
            status=OfferBoostRequest.STATUS_APPROVED,
            starts_at__lte=now,
            ends_at__gt=now,
        )
    ).order_by('-created_at').first()
    if existing:
        if existing.status == OfferBoostRequest.STATUS_PENDING:
            messages.info(request, "Une demande de boost est déjà en attente pour ce produit.")
        else:
            messages.info(request, "Ce produit est déjà boosté.")
        return redirect('pro_offers')

    if request.method == 'POST':
        form = OfferBoostRequestForm(request.POST)
        if form.is_valid():
            OfferBoostRequest.objects.create(
                offer=offer,
                requested_by=request.user,
                duration_days=int(form.cleaned_data['duration_days']),
                note=form.cleaned_data['note'],
            )
            messages.success(
                request,
                "Votre demande de boost a été envoyée aux administrateurs.",
            )
            return redirect('pro_offers')
    else:
        form = OfferBoostRequestForm()

    return render(request, 'tracker/pro_offer_boost_request.html', {
        'profile': profile,
        'offer': offer,
        'form': form,
    })


@login_required
def pro_offer_create(request):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    if request.method == 'POST':
        form = QuickOfferForm(request.POST, request.FILES)
        if form.is_valid():
            offer = Offer.objects.create(
                business=profile,
                offer_type=form.cleaned_data['offer_type'],
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                price=form.cleaned_data['price'],
                currency=form.cleaned_data['currency'],
                price_unit=form.cleaned_data['price_unit'],
                availability=form.cleaned_data['availability'],
                primary_image_url=form.cleaned_data['primary_image_url'],
                external_url=form.cleaned_data['external_url'],
                whatsapp=form.cleaned_data['whatsapp'] or profile.whatsapp,
                contact_method='whatsapp' if (form.cleaned_data['whatsapp'] or profile.whatsapp) else ('external' if form.cleaned_data['external_url'] else 'business'),
                market_code=profile.market_code,
                city=profile.city,
            )
            _attach_offer_media(offer, form.cleaned_data.get('photos'))
            _sync_offer_product_bridge(offer)
            messages.success(request, "Votre offre a été publiée.")
            return redirect('pro_offers')
    else:
        form = QuickOfferForm(initial={
            'currency': get_market(profile.market_code).currency or 'USD',
            'whatsapp': profile.whatsapp,
        })
    return render(request, 'tracker/pro_offer_form.html', {
        'profile': profile,
        'form': form,
        'page_title': 'Publication rapide',
        'submit_label': 'Publier maintenant',
        'quick_mode': True,
    })


@login_required
def pro_offer_edit(request, offer_id):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    offer = get_object_or_404(Offer, pk=offer_id, business=profile)
    initial = {
        'offer_type': offer.offer_type,
        'title': offer.title,
        'price': offer.price,
        'currency': offer.currency,
        'price_unit': offer.price_unit,
        'primary_image_url': offer.primary_image_url,
        'availability': offer.availability,
        'whatsapp': offer.whatsapp,
        'external_url': offer.external_url,
        'description': offer.description,
        'category': offer.category,
        'city': offer.city,
        'contact_method': offer.contact_method,
    }
    if request.method == 'POST':
        form = OfferEditForm(request.POST, request.FILES)
        if form.is_valid():
            for field in (
                'offer_type', 'title', 'price', 'currency', 'price_unit',
                'primary_image_url', 'availability', 'whatsapp', 'external_url',
                'description', 'category', 'city', 'contact_method',
            ):
                setattr(offer, field, form.cleaned_data[field])
            offer.save()
            _attach_offer_media(offer, form.cleaned_data.get('photos'))
            _sync_offer_product_bridge(offer)
            messages.success(request, "Votre offre a été mise à jour.")
            return redirect('pro_offers')
    else:
        form = OfferEditForm(initial=initial)
    return render(request, 'tracker/pro_offer_form.html', {
        'profile': profile,
        'offer': offer,
        'form': form,
        'page_title': "Modifier l'offre",
        'submit_label': 'Enregistrer',
        'quick_mode': False,
        'media': list(offer.media.all()),
    })


@login_required
def pro_offer_media_action(request, offer_id, media_id, action):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    offer = get_object_or_404(Offer, pk=offer_id, business=profile)
    media = get_object_or_404(OfferMedia, pk=media_id, offer=offer)
    if request.method != 'POST':
        return redirect('pro_offer_edit', offer_id=offer.pk)

    if action == 'primary':
        media.is_primary = True
        media.save(update_fields=['is_primary'])
    elif action == 'delete':
        was_primary = media.is_primary
        for image_file in (media.file, media.optimized_file, media.thumbnail_file):
            if image_file:
                image_file.delete(save=False)
        media.delete()
        if was_primary:
            replacement = offer.media.order_by('position', 'created_at', 'pk').first()
            if replacement:
                replacement.is_primary = True
                replacement.save(update_fields=['is_primary'])
    elif action in {'up', 'down'}:
        ordered = list(offer.media.order_by('position', 'created_at', 'pk'))
        try:
            current_index = next(i for i, item in enumerate(ordered) if item.pk == media.pk)
        except StopIteration:
            return redirect('pro_offer_edit', offer_id=offer.pk)
        target_index = current_index - 1 if action == 'up' else current_index + 1
        if 0 <= target_index < len(ordered):
            ordered[current_index], ordered[target_index] = ordered[target_index], ordered[current_index]
            for index, item in enumerate(ordered):
                if item.position != index:
                    OfferMedia.objects.filter(pk=item.pk).update(position=index)
    return redirect('pro_offer_edit', offer_id=offer.pk)


@login_required
def pro_offer_toggle(request, offer_id):
    profile = _verified_business_profile(request)
    if profile is None:
        return redirect('business_account_request')
    offer = get_object_or_404(Offer, pk=offer_id, business=profile)
    if request.method == 'POST':
        offer.is_active = not offer.is_active
        offer.save(update_fields=['is_active', 'updated_at'])
        if offer.price_listing_id:
            PriceListing.objects.filter(pk=offer.price_listing_id).update(
                is_active=offer.is_active and offer.is_public
            )
    return redirect('pro_offers')


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
    first_party_offers = []
    unified_results = []
    discovery_sources = []
    errors = []
    summary = {}
    query = ""
    site = "all"
    market_code = DEFAULT_MARKET_CODE
    city = ""
    offer_type = ""
    source_filter = ""
    business_category = ""
    async_waiting = False
    async_active_jobs = 0
    search_run = None
    run_state = None
    discovery_page = None

    if request.method == "GET" and request.GET.get("q"):
        query = request.GET.get("q", "").strip()
        site = request.GET.get("site", "all").strip() or "all"
        market_code = normalize_market_code(request.GET.get("market", DEFAULT_MARKET_CODE))
        city = request.GET.get("city", "").strip()
        offer_type = request.GET.get("offer_type", "").strip()
        source_filter = request.GET.get("source", "").strip()
        business_category = request.GET.get("business_category", "").strip()
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
            "city": city,
            "offer_type": offer_type,
            "source": source_filter,
            "business_category": business_category,
        })
        first_party_offers = find_matching_offers(
            query,
            market_code=market_code,
            city=city,
            offer_type=offer_type,
            business_category=business_category,
            limit=12,
        )
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
        unified_results = build_unified_results(
            first_party_offers,
            listings,
            discovery_sources,
            source_filter=source_filter,
            offer_type=offer_type,
            city=city,
            business_category=business_category,
            limit=40,
        )

        return render(request, "tracker/scrape.html", {
            "form": form,
            "listings": listings,
            "first_party_offers": first_party_offers,
            "unified_results": unified_results,
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
            "active_city": city,
            "active_offer_type": offer_type,
            "active_source": source_filter,
            "active_business_category": business_category,
        })

    if request.method == "POST":
        if anonymous_search_used:
            return redirect("signup")
        form = SearchOrScrapeForm(request.POST)
        if form.is_valid():
            site = form.cleaned_data["site"]
            query = form.cleaned_data["query"].strip()
            market_code = normalize_market_code(form.cleaned_data["market"])
            city = form.cleaned_data.get("city", "").strip()
            offer_type = form.cleaned_data.get("offer_type", "").strip()
            source_filter = form.cleaned_data.get("source", "").strip()
            business_category = form.cleaned_data.get("business_category", "").strip()
            market = get_market(market_code)
            try:
                model_name = get_llm_model_reference()
            except LLMRequiredError:
                errors.append(LLM_PUBLIC_ERROR)
                model_name = None
            if model_name is not None:
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
                    if city:
                        params["city"] = city
                    if offer_type:
                        params["offer_type"] = offer_type
                    if source_filter:
                        params["source"] = source_filter
                    if business_category:
                        params["business_category"] = business_category
                    return redirect(f"/?{urlencode(params)}")
        if listings:
            listings, summary = _decorate_results(listings, query, site)
    else:
        form = SearchOrScrapeForm()
        if request.method == "GET":
            discovery_page = _public_discovery_feed(request, per_page=12)

    return render(request, "tracker/scrape.html", {
        "form": form,
        "listings": listings,
        "first_party_offers": first_party_offers,
        "unified_results": unified_results,
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
        "active_city": city,
        "active_offer_type": offer_type,
        "active_source": source_filter,
        "active_business_category": business_category,
        "discovery_page": discovery_page,
    })
