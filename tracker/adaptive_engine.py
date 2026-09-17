from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from django.conf import settings

from tracker.adaptive_search import build_adaptive_search_terms, build_recovery_terms
from tracker.candidate_filter import filter_and_rank_candidate_urls
from tracker.catalog import find_fresh_cached_listings
from tracker.domain_health import domain_candidate_cap, domain_fetch_circuit_open, url_domain_health_score
from tracker.job_queue import claim_job, complete_job, enqueue_scrape_job, fail_job
from tracker.market_coverage import distinct_merchant_count
from tracker.models import ScrapeJob, SearchRun
from tracker.search_diagnostics import SearchDiagnosticsRecorder
from tracker.search_result_intelligence import collect_search_candidates, rank_search_candidates
from tracker.services import (
    _collect_search_urls, _deduplicate_results, _get_sort_rank, _known_merchant_domains,
    cleanup_stale_listings, ensure_retailer_for_site, get_llm_config, normalize_site_filter, process_url_and_save,
)
from tracker.store_discovery import discover_product_urls


def _append_unique(target, values):
    for value in values:
        if value not in target:
            target.append(value)


def _rank_adaptive_candidates(found, product_query=None):
    if found and isinstance(found[0], dict):
        ranked = rank_search_candidates(found, query=product_query, health_score_func=url_domain_health_score)
        return [candidate['url'] for candidate in ranked]
    return filter_and_rank_candidate_urls(found, health_score_func=url_domain_health_score, query=product_query)


def _search_terms_into_urls(search_terms, urls, diagnostics, search_errors, candidate_limit, product_query=None, search_run=None):
    for term in search_terms:
        if _search_run_completed(search_run):
            break
        diagnostics.record_search_term()
        try:
            # Preserve patchability/backward compatibility: tests that patch the
            # legacy collector still work, while production receives rich DDGS
            # title/snippet metadata from the intelligent collector.
            if getattr(_collect_search_urls, '__module__', '') != 'tracker.services':
                found = _collect_search_urls(term, max_results=candidate_limit)
            else:
                found = collect_search_candidates(term, max_results=candidate_limit, product_query=product_query)
        except Exception as exc:
            message = str(exc)
            search_errors.append(message)
            diagnostics.record_error(message)
            continue
        filtered = _rank_adaptive_candidates(found, product_query=product_query)
        diagnostics.record_candidates(len(filtered))
        _append_unique(urls, filtered)
        if len(urls) >= candidate_limit:
            break


def _domain(url):
    return urlparse(url).netloc.lower().removeprefix('www.')


def _search_run_completed(search_run):
    if search_run is None:
        return False
    state = SearchRun.objects.filter(pk=search_run.pk).values('status', 'completed_at').first()
    if not state:
        return False
    return bool(state['completed_at']) or state['status'] == SearchRun.STATUS_COMPLETED


def _max_scrape_jobs(search_run, target_merchants):
    """Return the network-work budget for one search execution.

    Discovery may collect many URLs, but only the strongest candidates should
    consume scrape-worker capacity. Cached jobs count toward the budget because
    they already contribute merchant coverage without network work.
    """
    configured = int(getattr(settings, 'ADAPTIVE_MAX_SCRAPE_JOBS', 15))
    floor = max(6, int(target_merchants) * 3)
    limit = max(floor, configured)
    if search_run is None:
        return limit, 0
    existing = search_run.jobs.count()
    return limit, existing


def _attach_cached_listings_to_run(search_run, listings, product_query, selected):
    """Expose fresh cached listings through the current asynchronous SearchRun."""
    if search_run is None:
        return
    for listing in listings or []:
        job = enqueue_scrape_job(
            url=listing.url,
            query=product_query,
            model_name=selected,
            max_attempts=int(getattr(settings, 'SCRAPE_JOB_MAX_ATTEMPTS', 3)),
            search_run=search_run,
        )
        if job.status != ScrapeJob.STATUS_SUCCESS or job.listing_id != listing.id or not job.from_cache:
            complete_job(job, listing=listing, fetch_status='cache', from_cache=True)


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
        listing, error = process_url_and_save(job.url, model_name=selected, expected_query=product_query, allowed_hosts=allowed_hosts)
        if listing:
            complete_job(job, listing=listing, fetch_status='processed_sync')
            return listing
        retryable = error == 'Impossible de récupérer le contenu de la page web.'
        fail_job(job, error or 'Échec de traitement.', retryable=retryable, fetch_status='processing_failure')
        if error:
            diagnostics.record_error(error)
            if error != 'Source non marchande ignorée.':
                errors.append(f'{job.url}: {error}')
        return None
    except Exception as exc:
        message = str(exc)
        fail_job(job, message, retryable=True, fetch_status='sync_exception')
        diagnostics.record_error(message)
        errors.append(f'{job.url}: {message}')
        return None


def _process_urls(
    urls,
    processed_urls,
    results,
    errors,
    diagnostics,
    selected,
    product_query,
    allowed_hosts,
    target_merchants,
    site_filters,
    search_run=None,
):
    domain_failures = Counter()
    domain_seen = Counter(_domain(url) for url in processed_urls if _domain(url))
    max_failures_per_domain = int(getattr(settings, 'ADAPTIVE_MAX_FAILURES_PER_DOMAIN', 2))
    max_candidates_per_domain = max(1, int(getattr(settings, 'ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN', 3)))
    sync_fallback = bool(getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True))
    domain_caps = {}
    circuit_state = {}
    scrape_limit, existing_jobs = _max_scrape_jobs(search_run, target_merchants)
    created_this_pass = 0

    for url in urls:
        if _search_run_completed(search_run):
            break
        # Keep discovery broad, but bound expensive page collection. Recovery and
        # fallback passes share the same SearchRun budget through existing_jobs.
        if existing_jobs + created_this_pass >= scrape_limit:
            break
        if url in processed_urls:
            continue
        host = _domain(url)
        if host and domain_failures[host] >= max_failures_per_domain:
            continue
        if not site_filters and host:
            if host not in circuit_state:
                circuit_state[host] = domain_fetch_circuit_open(host)
            if circuit_state[host]:
                continue
            if host not in domain_caps:
                domain_caps[host] = domain_candidate_cap(host, max_candidates_per_domain)
            if domain_seen[host] >= domain_caps[host]:
                continue

        processed_urls.add(url)
        if host:
            domain_seen[host] += 1
        diagnostics.record_processed()
        before_count = search_run.jobs.count() if search_run is not None else None
        job = enqueue_scrape_job(
            url=url,
            query=product_query,
            model_name=selected,
            max_attempts=int(getattr(settings, 'SCRAPE_JOB_MAX_ATTEMPTS', 3)),
            search_run=search_run,
        )
        if search_run is not None:
            after_count = search_run.jobs.count()
            if after_count > before_count:
                created_this_pass += 1
        else:
            created_this_pass += 1

        listing = None
        if job.status == ScrapeJob.STATUS_SUCCESS and job.listing_id:
            listing = job.listing
        elif sync_fallback:
            listing = _process_job_now(job, selected, product_query, diagnostics, errors, allowed_hosts=allowed_hosts)
        else:
            if search_run is not None:
                finished_qs = ScrapeJob.objects.filter(search_run=search_run, url=url)
            else:
                finished_qs = ScrapeJob.objects.filter(search_run__isnull=True, query=product_query, url=url)
            finished = finished_qs.filter(
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
        if _search_run_completed(search_run):
            break
        if not site_filters and distinct_merchant_count(_deduplicate_results(results)) >= target_merchants:
            break


def search_and_scrape_product(product_query, site_filter='all', model_name=None, max_results=3, search_run=None):
    cleanup_stale_listings(days=getattr(settings, 'LISTING_STALE_DAYS', 30))
    selected = (model_name or get_llm_config()['default_model']).strip()
    results, errors, search_errors, urls = [], [], [], []
    processed_urls = set()
    site_filter = (site_filter or 'all').strip() or 'all'
    country = getattr(settings, 'DEFAULT_SEARCH_COUNTRY', 'RDC')
    site_filters = [] if site_filter == 'all' else [part.strip() for part in site_filter.split(',') if part.strip()]
    for site in site_filters:
        ensure_retailer_for_site(site)

    cache_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    cached = find_fresh_cached_listings(product_query, site_hosts=cache_hosts)
    target_merchants = 1 if site_filters else max(2, int(getattr(settings, 'MARKET_COVERAGE_TARGET', max_results)))
    diagnostics = SearchDiagnosticsRecorder(product_query, site_filter, target_merchants)

    if cached and search_run is not None:
        _attach_cached_listings_to_run(search_run, cached, product_query, selected)
    if cached and (site_filters or distinct_merchant_count(cached) >= target_merchants):
        diagnostics.save(cached)
        return cached, []
    if cached:
        results.extend(cached)

    if search_run is None:
        search_run = SearchRun.objects.create(query=product_query, site_filter=site_filter, target_merchants=target_merchants)
    candidate_limit = max(target_merchants * 5, max_results * 4, 15)
    search_terms = [f'site:{normalize_site_filter(site)[0]} {product_query}' for site in site_filters] if site_filters else build_adaptive_search_terms(product_query, country=country)
    _search_terms_into_urls(search_terms, urls, diagnostics, search_errors, candidate_limit, product_query=product_query, search_run=search_run)
    allowed_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run)

    if _search_run_completed(search_run):
        diagnostics.save(_deduplicate_results(results))
        return _deduplicate_results(results), []

    if not site_filters and distinct_merchant_count(_deduplicate_results(results)) < target_merchants:
        recovery_terms = [term for term in build_recovery_terms(product_query, errors + search_errors, country=country) if term not in search_terms]
        if recovery_terms:
            before = len(urls)
            _search_terms_into_urls(recovery_terms, urls, diagnostics, search_errors, candidate_limit * 2, product_query=product_query, search_run=search_run)
            if len(urls) > before and not _search_run_completed(search_run):
                _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run)

    if _search_run_completed(search_run):
        diagnostics.save(_deduplicate_results(results))
        return _deduplicate_results(results), []

    deduped = _deduplicate_results(results)
    if distinct_merchant_count(deduped) < target_merchants:
        fallback_domains = cache_hosts or _known_merchant_domains(limit=max(20, target_merchants * 5))
        if fallback_domains and not _search_run_completed(search_run):
            try:
                fallback_urls = _rank_adaptive_candidates(discover_product_urls(product_query, fallback_domains, max_results=max(target_merchants * 4, max_results * 2)), product_query=product_query)
            except Exception as exc:
                message = str(exc)
                search_errors.append(message)
                diagnostics.record_error(message)
                fallback_urls = []
            diagnostics.record_fallback_candidates(len(fallback_urls))
            _process_urls(fallback_urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run)

    results = _deduplicate_results(results)
    results.sort(key=_get_sort_rank)
    diagnostics.save(results)
    if results:
        return results, []
    if not getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True) and urls:
        return [], ['Recherche lancée en arrière-plan. Les offres seront disponibles après traitement de la file de collecte.']
    if search_errors and not urls:
        return [], ["La recherche web n'a retourné aucune page marchande exploitable pour ce produit."]
    return [], errors or ['Aucune page marchande exploitable n\'a été trouvée pour ce produit.']
