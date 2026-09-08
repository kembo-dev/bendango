from __future__ import annotations

import time
from collections import Counter

from tracker.market_coverage import distinct_merchant_count
from tracker.models import SearchDiagnostic


def classify_search_error(message: str) -> str:
    text = (message or "").lower()
    if "introuvable" in text or "404" in text:
        return "not_found"
    if "non pertinent" in text:
        return "product_mismatch"
    if "invalides" in text:
        return "invalid_data"
    if "structure de produit" in text:
        return "no_product_structure"
    if "extraction a échoué" in text:
        return "extraction_failed"
    if "impossible de récupérer" in text:
        return "fetch_failed"
    if "source non marchande" in text:
        return "non_commerce"
    if "aucune url" in text or "aucune page" in text or "recherche web" in text:
        return "no_candidates"
    return "other"


class SearchDiagnosticsRecorder:
    def __init__(self, query: str, site_filter: str, target_merchants: int):
        self.query = query
        self.site_filter = site_filter or "all"
        self.target_merchants = max(1, int(target_merchants or 1))
        self.started_at = time.monotonic()
        self.search_terms = 0
        self.candidate_urls = 0
        self.processed_urls = 0
        self.fallback_urls = 0
        self.errors = []

    def record_search_term(self):
        self.search_terms += 1

    def record_candidates(self, count: int):
        self.candidate_urls += max(0, int(count or 0))

    def record_processed(self):
        self.processed_urls += 1

    def record_fallback_candidates(self, count: int):
        self.fallback_urls += max(0, int(count or 0))

    def record_error(self, message: str):
        if message:
            self.errors.append(message)

    def save(self, listings):
        reasons = Counter(classify_search_error(error) for error in self.errors)
        merchant_count = distinct_merchant_count(listings)
        coverage_ratio = min(1.0, merchant_count / self.target_merchants)
        return SearchDiagnostic.objects.create(
            query=self.query[:255],
            site_filter=self.site_filter[:255],
            search_terms_count=self.search_terms,
            candidate_urls_count=self.candidate_urls,
            processed_urls_count=self.processed_urls,
            fallback_urls_count=self.fallback_urls,
            offers_count=len(listings),
            merchant_count=merchant_count,
            target_merchants=self.target_merchants,
            coverage_ratio=coverage_ratio,
            rejection_reasons=dict(reasons),
            duration_ms=max(0, round((time.monotonic() - self.started_at) * 1000)),
        )
