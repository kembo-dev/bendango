from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from django.conf import settings

from tracker.adaptive_search import build_adaptive_search_terms, build_recovery_terms
from tracker.candidate_filter import filter_and_rank_candidate_urls
from tracker.catalog import find_fresh_cached_listings
from tracker.domain_health import url_domain_health_score
from tracker.job_queue import claim_job, complete_job, enqueue_scrape_job, fail_job
from tracker.market_coverage import distinct_merchant_count
from tracker.models import ScrapeJob
from tracker.search_diagnostics import SearchDiagnosticsRecorder
from tracker.services import (
    _collect_search_urls,
    _deduplicate_results,
    _get_sort_rank,
    _known_merchant_domains,
    cleanup_stale_listings,
    ensure_retailer_for_site,
    get_llm_config,
    normalize_site_filter,
    process_url_and_save,
)
from tracker.store_discovery import discover_product_urls


def _append_unique(target, values):
    for value in values:
        if value not in target:
            target.append(value)


def _rank_adaptive_candidates(found):
    return filter_and_rank_candidate_urls(found, health_score_func=url_domain_health_score)


def _search_terms_into_urls(search_terms, urls, diagnostics, search_errors, candidate_limit):
    for term in search_terms:
        diagnostics.record_search_term()
        try:
            found = _collect_search_urls(term, max_results=candidate_limit)
        except Exception as exc:
            message = str(exc)
            search_errors.append(message)
            diagnostics.record_error(message)
            continue
        filtered = _rank_adaptive_candidates(found)
        diagnostics.record_candidates(len(filtered))
        _append_unique(urls, filtered)
        if len(urls) >= candidate_limit:
            break


def _domain(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def _process_job_now(job, selected, product_query, diagnostics, errors, allowed_hosts=None):
    if job.status == ScrapeJob.STATUS_SUCCESS and job.listing_id:
        return job.listing

    claimed = claim_job(job.pk)
    if claimed is None:
        current = ScrapeJob.objects.filter(pk=job.pk).select_related('listing').first()
        if current and current.status == ScrapeJob.STATUS_SUCCESS and current.listing_id:
            return current.listing
        return None
    job = claimed

    try:
        listing, error = process_url_and_save(
            job.url,
            model_name=selected,
            expected_query=product_query,
            allowed_hosts=allowed_hosts,
        )
        if listing:
            complete_job(job, listing=listing, fetch_status='processed_sync')
            return listing

        retryable = error == 'Impossible de récupérer le contenu de la page web.'
        fail_job(job, error or "Échec de traitement.", retryable=retryable, fetch_status='processing_failure')
        if error:
            diagnostics.record_error(error)
            if error != "Source non marchande ignorée.":
                errors.append(f"{job.url}: {error}")
        return None
    except Exception as exc:
        message = str(exc)
        fail_job(job, message, retryable=True, fetch_status='sync_exception')
        diagnostics.record_error(message)
        errors.append(f"{job.url}: {message}")
        return None


def _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters):
    domain_failures = Counter()
    max_failures_per_domain = int(getattr(settings, "ADAPTIVE_MAX_FAILURES_PER_DOMAIN", 2))
    sync_fallback = bool(getattr(settings, "SCRAPE_QUEUE_SYNC_FALLBACK", True))

    for url in urls:
        if url in processed_urls:
            continue
        host = _domain(url)
        if host and domain_failures[host] >= max_failures_per_domain:
            continue

        processed_urls.add(url)
        diagnostics.record_processed()
        job = enqueue_scrape_job(
            url=url,
            query=product_query,
            model_name=selected,
            max_attempts=int(getattr(settings, "SCRAPE_JOB_MAX_ATTEMPTS", 3)),
        )

        listing = None
        if job.status == ScrapeJob.STATUS_SUCCESS and job.listing_id:
            listing = job.listing
        elif sync_fallback:
            listing = _process_job_now(job, selected, product_query, diagnostics, errors, allowed_hosts=allowed_hosts)
        else:
            finished = ScrapeJob.objects.filter(
                url=url,
                query=product_query,
                status=ScrapeJob.STATUS_SUCCESS,
                listing__isnull=False,
            ).select_related('listing').order_by('-finished_at').first()
            if finished:
                listing = finished.listing

        if listing:
            results.append(listing)
        else:
            current = ScrapeJob.objects.filter(pk=job.pk).first()
            if current and current.status == ScrapeJob.STATUS_FAILED and host:
                domain_failures[host] += 1

        if not site_filters and distinct_merchant_count(_deduplicate_results(results)) >= target_merchants:
            break


def search_and_scrape_product(product_query, site_filter="all", model_name=None, max_results=3):
    cleanup_stale_listings(days=getattr(settings, "LISTING_STALE_DAYS", 30))
    selected = (model_name or get_llm_config()["default_model"]).strip()
    results = []
    errors = []
    search_errors = []
    urls = []
    processed_urls = set()

    site_filter = (site_filter or "all").strip() or "all"
    country = getattr(settings, "DEFAULT_SEARCH_COUNTRY", "RDC")
    site_filters = [] if site_filter == "all" else [part.strip() for part in site_filter.split(",") if part.strip()]
    for site in site_filters:
        ensure_retailer_for_site(site)

    cache_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    cached = find_fresh_cached_listings(product_query, site_hosts=cache_hosts)
    target_merchants = 1 if site_filters else max(2, int(getattr(settings, "MARKET_COVERAGE_TARGET", max_results)))
    diagnostics = SearchDiagnosticsRecorder(product_query, site_filter, target_merchants)

    if cached and (site_filters or distinct_merchant_count(cached) >= target_merchants):
        diagnostics.save(cached)
        return cached, []
    if cached:
        results.extend(cached)

    candidate_limit = max(target_merchants * 8, max_results * 6, 18)
    if site_filters:
        search_terms = [f"site:{normalize_site_filter(site)[0]} {product_query}" for site in site_filters]
    else:
        search_terms = build_adaptive_search_terms(product_query, country=country)

    _search_terms_into_urls(search_terms, urls, diagnostics, search_errors, candidate_limit)
    allowed_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters)

    if not site_filters and distinct_merchant_count(_deduplicate_results(results)) < target_merchants:
        recovery_terms = build_recovery_terms(product_query, errors + search_errors, country=country)
        recovery_terms = [term for term in recovery_terms if term not in search_terms]
        if recovery_terms:
            before = len(urls)
            _search_terms_into_urls(recovery_terms, urls, diagnostics, search_errors, candidate_limit * 2)
            if len(urls) > before:
                _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters)

    deduped = _deduplicate_results(results)
    if distinct_merchant_count(deduped) < target_merchants:
        fallback_domains = cache_hosts or _known_merchant_domains(limit=max(20, target_merchants * 5))
        if fallback_domains:
            try:
                fallback_urls = _rank_adaptive_candidates(discover_product_urls(
                    product_query,
                    fallback_domains,
                    max_results=max(target_merchants * 4, max_results * 2),
                ))
            except Exception as exc:
                message = str(exc)
                search_errors.append(message)
                diagnostics.record_error(message)
                fallback_urls = []
            diagnostics.record_fallback_candidates(len(fallback_urls))
            _process_urls(fallback_urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters)

    results = _deduplicate_results(results)
    results.sort(key=_get_sort_rank)
    diagnostics.save(results)
    if results:
        return results, []
    if not getattr(settings, "SCRAPE_QUEUE_SYNC_FALLBACK", True) and urls:
        return [], ["Recherche lancée en arrière-plan. Les offres seront disponibles après traitement de la file de collecte."]
    if search_errors and not urls:
        return [], ["La recherche web n'a retourné aucune page marchande exploitable pour ce produit."]
    return [], errors or ["Aucune page marchande exploitable n'a été trouvée pour ce produit."]
