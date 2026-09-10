from __future__ import annotations


def classify_processing_error(error: str | None) -> tuple[str, bool]:
    """Map user-facing processing errors to stable operational categories.

    Returns (fetch_status, retryable). The categories are intentionally compact so
    monitoring can aggregate them across workers and releases.
    """
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
