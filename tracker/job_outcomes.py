from __future__ import annotations

from django.conf import settings


def classify_processing_error(error: str | None) -> tuple[str, bool]:
    """Map user-facing processing errors to stable operational categories."""
    text = (error or "").strip().lower()
    if not text:
        return "processing_failure", False

    if "protection anti-bot" in text or "captcha" in text or "anti-bot" in text:
        return "anti_bot", True
    if "impossible de récupérer le contenu" in text or "impossible de recuperer le contenu" in text:
        return "fetch_failed", True
    if "page introuvable" in text or "url produit inexistante" in text:
        return "not_found", False
    if "sans structure de produit exploitable" in text:
        return "no_product_structure", False
    if "produit non pertinent" in text or "similarité insuffisante" in text or "similarite insuffisante" in text:
        return "product_mismatch", False
    if "données extraites invalides" in text or "donnees extraites invalides" in text:
        return "invalid_data", False
    if "extraction a échoué" in text or "extraction a echoue" in text:
        return "extraction_failed", False
    if "source non marchande" in text:
        return "non_merchant", False
    if "liste ou catégorie" in text or "liste ou categorie" in text:
        return "listing_page", False
    if "page d'accueil" in text:
        return "homepage", False

    return "processing_failure", False


def should_retry_job(fetch_status: str, attempts: int, retryable: bool) -> bool:
    """Decide whether the persistent queue should retry after inner fetch retries.

    The HTTP collector already retries transient network failures internally. By
    default the persistent queue therefore grants at most one additional delayed
    attempt for fetch/anti-bot failures, instead of multiplying 3 transport attempts
    by 3 queue attempts.
    """
    if not retryable:
        return False
    if fetch_status in {"fetch_failed", "anti_bot"}:
        max_queue_attempts = max(1, int(getattr(settings, "SCRAPE_JOB_FETCH_MAX_ATTEMPTS", 2)))
        return int(attempts or 0) < max_queue_attempts
    return True
