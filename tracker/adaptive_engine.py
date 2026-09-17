from __future__ import annotations

import time
from collections import Counter
from urllib.parse import urlparse

from django.conf import settings

from tracker.adaptive_search import build_adaptive_search_terms, build_recovery_terms
from tracker.candidate_filter import filter_and_rank_candidate_urls
from tracker.catalog import find_fresh_cached_listings
from tracker.domain_health import domain_candidate_cap, domain_fetch_circuit_open, url_domain_health_score
from tracker.job_queue import claim_job, complete_job, enqueue_scrape_job, fail_job
from tracker.market_coverage import distinct_merchant_count
from tracker.markets import DEFAULT_MARKET_CODE, get_market, normalize_market_code
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


def _search_terms_into_urls(
    search_terms,
    urls,
    diagnostics,
    search_errors,
    candidate_limit,
    product_query=None,
    search_run=None,
    stop_on_first_candidates=False,
):
    """Collect candidate URLs, optionally returning after the first useful batch.

    Initial async discovery should enqueue work as soon as possible instead of
    spending the whole SearchRun budget executing every web-search term before
    scrape workers receive anything. Recovery passes may still aggregate more
    terms when broader coverage is required.
    """
    for term in search_terms:
        if _search_run_completed(search_run):
            break
        diagnostics.record_search_term()
        try:
            found = (
                _collect_search_urls(term, max_results=candidate_limit)
                if getattr(_collect_search_urls, '__module__', '') != 'tracker.services'
                else collect_search_candidates(
                    term,
                    max_results=candidate_limit,
                    product_query=product_query,
                )
            )
        except Exception as exc:
            message = str(exc)
            search_errors.append(message)
            diagnostics.record_error(message)
            continue
        filtered = _rank_adaptive_candidates(found, product_query=product_query)
        diagnostics.record_candidates(len(filtered))
        before = len(urls)
        _append_unique(urls, filtered)
        if stop_on_first_candidates and len(urls) > before:
            break
        if len(urls) >= candidate_limit:
            break


def _domain(url): return urlparse(url).netloc.lower().removeprefix('www.')


def _search_run_completed(search_run):
    if search_run is None: return False
    state = SearchRun.objects.filter(pk=search_run.pk).values('status', 'completed_at').first()
    return bool(state and (state['completed_at'] or state['status'] == SearchRun.STATUS_COMPLETED))


def _successful_run_listings(search_run):
    if search_run is None: return []
    successful = ScrapeJob.objects.filter(search_run=search_run, status=ScrapeJob.STATUS_SUCCESS, listing__isnull=False).select_related('listing', 'listing__retailer')
    return [job.listing for job in successful if job.listing_id]


def _successful_run_merchants(search_run): return distinct_merchant_count(_successful_run_listings(search_run))


def _run_has_active_jobs(search_run):
    return bool(search_run and search_run.jobs.filter(status__in=[ScrapeJob.STATUS_PENDING, ScrapeJob.STATUS_RUNNING, ScrapeJob.STATUS_RETRY]).exists())


def _partial_async_coverage_exhausted(search_run):
    if search_run is None or getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True): return False
    return _successful_run_merchants(search_run) > 0 and not _run_has_active_jobs(search_run)


def _wait_for_batch(search_run, target_merchants, timeout_seconds=None):
    if search_run is None or getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True): return _search_run_completed(search_run)
    timeout_seconds = float(getattr(settings, 'ADAPTIVE_BATCH_WAIT_SECONDS', 8)) if timeout_seconds is None else timeout_seconds
    deadline = time.monotonic() + max(0.0, float(timeout_seconds)); poll = max(0.1, float(getattr(settings, 'ADAPTIVE_BATCH_POLL_SECONDS', 0.5)))
    while time.monotonic() < deadline:
        if _search_run_completed(search_run) or _successful_run_merchants(search_run) >= target_merchants: return True
        if not _run_has_active_jobs(search_run): return False
        time.sleep(poll)
    return _search_run_completed(search_run) or _successful_run_merchants(search_run) >= target_merchants


def _max_scrape_jobs(search_run, target_merchants):
    configured = int(getattr(settings, 'ADAPTIVE_MAX_SCRAPE_JOBS', 15)); floor = max(6, int(target_merchants) * 3); limit = max(floor, configured)
    return (limit, search_run.jobs.count() if search_run is not None else 0)


def _attach_cached_listings_to_run(search_run, listings, product_query, selected):
    if search_run is None: return
    for listing in listings or []:
        job = enqueue_scrape_job(url=listing.url, query=product_query, model_name=selected, max_attempts=int(getattr(settings, 'SCRAPE_JOB_MAX_ATTEMPTS', 3)), search_run=search_run)
        if job.status != ScrapeJob.STATUS_SUCCESS or job.listing_id != listing.id or not job.from_cache: complete_job(job, listing=listing, fetch_status='cache', from_cache=True)


def _process_job_now(job, selected, product_query, diagnostics, errors, allowed_hosts=None):
    if job.status == ScrapeJob.STATUS_SUCCESS and job.listing_id: return job.listing
    claimed = claim_job(job.pk)
    if claimed is None:
        current = ScrapeJob.objects.filter(pk=job.pk).select_related('listing').first()
        return current.listing if current and current.status == ScrapeJob.STATUS_SUCCESS and current.listing_id else None
    job = claimed
    try:
        listing, error = process_url_and_save(job.url, model_name=selected, expected_query=product_query, allowed_hosts=allowed_hosts)
        if listing: complete_job(job, listing=listing, fetch_status='processed_sync'); return listing
        fail_job(job, error or 'Échec de traitement.', retryable=error == 'Impossible de récupérer le contenu de la page web.', fetch_status='processing_failure')
        if error:
            diagnostics.record_error(error)
            if error != 'Source non marchande ignorée.': errors.append(f'{job.url}: {error}')
        return None
    except Exception as exc:
        message = str(exc); fail_job(job, message, retryable=True, fetch_status='sync_exception'); diagnostics.record_error(message); errors.append(f'{job.url}: {message}'); return None


def _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run=None, max_new_jobs=None):
    domain_failures = Counter(); domain_seen = Counter(_domain(url) for url in processed_urls if _domain(url))
    max_failures_per_domain = int(getattr(settings, 'ADAPTIVE_MAX_FAILURES_PER_DOMAIN', 2)); max_candidates_per_domain = max(1, int(getattr(settings, 'ADAPTIVE_MAX_CANDIDATES_PER_DOMAIN', 3)))
    sync_fallback = bool(getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True)); domain_caps = {}; circuit_state = {}
    scrape_limit, existing_jobs = _max_scrape_jobs(search_run, target_merchants); created_this_pass = 0; pass_limit = scrape_limit if max_new_jobs is None else max(0, int(max_new_jobs))
    for url in urls:
        if _search_run_completed(search_run) or existing_jobs + created_this_pass >= scrape_limit or created_this_pass >= pass_limit: break
        if url in processed_urls: continue
        host = _domain(url)
        if host and domain_failures[host] >= max_failures_per_domain: continue
        if not site_filters and host:
            if host not in circuit_state: circuit_state[host] = domain_fetch_circuit_open(host)
            if circuit_state[host]: continue
            if host not in domain_caps: domain_caps[host] = domain_candidate_cap(host, max_candidates_per_domain)
            if domain_seen[host] >= domain_caps[host]: continue
        processed_urls.add(url)
        if host: domain_seen[host] += 1
        diagnostics.record_processed(); before_count = search_run.jobs.count() if search_run is not None else None
        job = enqueue_scrape_job(url=url, query=product_query, model_name=selected, max_attempts=int(getattr(settings, 'SCRAPE_JOB_MAX_ATTEMPTS', 3)), search_run=search_run)
        if search_run is not None:
            if search_run.jobs.count() > before_count: created_this_pass += 1
        else: created_this_pass += 1
        listing = job.listing if job.status == ScrapeJob.STATUS_SUCCESS and job.listing_id else None
        if not listing and sync_fallback: listing = _process_job_now(job, selected, product_query, diagnostics, errors, allowed_hosts=allowed_hosts)
        elif not listing and not sync_fallback:
            finished_qs = ScrapeJob.objects.filter(search_run=search_run, url=url) if search_run is not None else ScrapeJob.objects.filter(search_run__isnull=True, query=product_query, url=url)
            finished = finished_qs.filter(status=ScrapeJob.STATUS_SUCCESS, listing__isnull=False).select_related('listing').order_by('-finished_at').first()
            if finished: listing = finished.listing
        if listing: results.append(listing)
        else:
            current = ScrapeJob.objects.filter(pk=job.pk).first()
            if current and current.status == ScrapeJob.STATUS_FAILED and host: domain_failures[host] += 1
        if _search_run_completed(search_run) or (not site_filters and distinct_merchant_count(_deduplicate_results(results)) >= target_merchants): break
    return created_this_pass


def search_and_scrape_product(product_query, site_filter='all', model_name=None, max_results=3, search_run=None, market_code=None):
    cleanup_stale_listings(days=getattr(settings, 'LISTING_STALE_DAYS', 30)); selected = (model_name or get_llm_config()['default_model']).strip()
    results, errors, search_errors, urls = [], [], [], []; processed_urls = set(); site_filter = (site_filter or 'all').strip() or 'all'
    market_code = normalize_market_code(market_code or (getattr(search_run, 'market_code', None) if search_run else None) or DEFAULT_MARKET_CODE); market = get_market(market_code); country = market.country
    site_filters = [] if site_filter == 'all' else [part.strip() for part in site_filter.split(',') if part.strip()]
    for site in site_filters: ensure_retailer_for_site(site)
    cache_hosts = [normalize_site_filter(site)[0] for site in site_filters]; cached = find_fresh_cached_listings(product_query, site_hosts=cache_hosts, market_code=market.code)
    target_merchants = 1 if site_filters else max(2, int(getattr(settings, 'MARKET_COVERAGE_TARGET', max_results))); diagnostics = SearchDiagnosticsRecorder(product_query, site_filter, target_merchants)
    if cached and search_run is not None: _attach_cached_listings_to_run(search_run, cached, product_query, selected)
    if cached and (site_filters or distinct_merchant_count(cached) >= target_merchants): diagnostics.save(cached); return cached, []
    if cached: results.extend(cached)
    if search_run is None: search_run = SearchRun.objects.create(query=product_query, site_filter=site_filter, target_merchants=target_merchants, market_code=market.code, market_currency=market.currency)
    candidate_limit = max(target_merchants * 5, max_results * 4, 15)
    search_terms = [f'site:{normalize_site_filter(site)[0]} {product_query}' for site in site_filters] if site_filters else build_adaptive_search_terms(product_query, country=country)
    _search_terms_into_urls(
        search_terms,
        urls,
        diagnostics,
        search_errors,
        candidate_limit,
        product_query=product_query,
        search_run=search_run,
        stop_on_first_candidates=True,
    )
    allowed_hosts = [normalize_site_filter(site)[0] for site in site_filters]
    initial_batch = max(1, int(getattr(settings, 'ADAPTIVE_INITIAL_SCRAPE_JOBS', 8))); expansion_batch = max(1, int(getattr(settings, 'ADAPTIVE_EXPANSION_SCRAPE_JOBS', 5)))
    _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run, max_new_jobs=initial_batch)
    if not _search_run_completed(search_run): _wait_for_batch(search_run, target_merchants)
    if _search_run_completed(search_run):
        db_results = _deduplicate_results([*results, *_successful_run_listings(search_run)]); diagnostics.save(db_results); return db_results, []
    _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run, max_new_jobs=expansion_batch)
    if not _search_run_completed(search_run): _wait_for_batch(search_run, target_merchants)
    if _search_run_completed(search_run) or _partial_async_coverage_exhausted(search_run):
        db_results = _deduplicate_results([*results, *_successful_run_listings(search_run)]); diagnostics.save(db_results); return db_results, []
    if not site_filters and distinct_merchant_count(_deduplicate_results(results)) < target_merchants:
        recovery_terms = [term for term in build_recovery_terms(product_query, errors + search_errors, country=country) if term not in search_terms]
        if recovery_terms:
            before = len(urls); _search_terms_into_urls(recovery_terms, urls, diagnostics, search_errors, candidate_limit * 2, product_query=product_query, search_run=search_run)
            if len(urls) > before and not _search_run_completed(search_run): _process_urls(urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run)
    if _search_run_completed(search_run):
        db_results = _deduplicate_results([*results, *_successful_run_listings(search_run)]); diagnostics.save(db_results); return db_results, []
    deduped = _deduplicate_results([*results, *_successful_run_listings(search_run)])
    if distinct_merchant_count(deduped) < target_merchants:
        fallback_domains = cache_hosts or _known_merchant_domains(limit=max(20, target_merchants * 5))
        if fallback_domains and not _search_run_completed(search_run):
            try: fallback_urls = _rank_adaptive_candidates(discover_product_urls(product_query, fallback_domains, max_results=max(target_merchants * 4, max_results * 2)), product_query=product_query)
            except Exception as exc: message = str(exc); search_errors.append(message); diagnostics.record_error(message); fallback_urls = []
            diagnostics.record_fallback_candidates(len(fallback_urls)); _process_urls(fallback_urls, processed_urls, results, errors, diagnostics, selected, product_query, allowed_hosts, target_merchants, site_filters, search_run)
    results = _deduplicate_results([*results, *_successful_run_listings(search_run)]); results.sort(key=_get_sort_rank); diagnostics.save(results)
    if results: return results, []
    if not getattr(settings, 'SCRAPE_QUEUE_SYNC_FALLBACK', True) and urls: return [], ['Recherche lancée en arrière-plan. Les offres apparaîtront dès que les pages marchandes auront été analysées.']
    return [], errors or search_errors or ['Aucun produit correspondant trouvé.']
