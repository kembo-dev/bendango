from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache


TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
ANTI_BOT_MARKERS = (
    "captcha",
    "verify you are human",
    "verification required",
    "access denied",
    "cloudflare ray id",
    "checking your browser",
    "unusual traffic",
    "robot check",
)


@dataclass(frozen=True)
class FetchResult:
    html: str | None
    status: str
    http_status: int | None = None
    attempts: int = 0
    from_cache: bool = False
    duration_ms: int = 0
    error: str = ""


def build_headers():
    return {
        "User-Agent": getattr(settings, "COLLECTION_USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }


def _cache_key(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"bendango:html:{digest}"


def _domain_key(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.") or "unknown"
    return f"bendango:domain:last_fetch:{host}"


def _wait_for_domain_slot(url: str):
    interval = float(getattr(settings, "COLLECTION_DOMAIN_MIN_INTERVAL", 0.35))
    if interval <= 0:
        return
    key = _domain_key(url)
    now = time.monotonic()
    last = cache.get(key)
    if last is not None:
        remaining = interval - (now - float(last))
        if remaining > 0:
            time.sleep(remaining)
    cache.set(key, time.monotonic(), timeout=max(int(interval * 20), 10))


def _clean_html(content: bytes, encoding: str | None = None) -> str:
    selected = encoding if isinstance(encoding, str) else "utf-8"
    try:
        text = content.decode(selected, errors="replace")
    except (LookupError, TypeError):
        text = content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(text, "html.parser")
    for element in soup(["style", "svg", "noscript", "header", "footer", "nav"]):
        element.decompose()
    return str(soup)[:120000]


def _is_anti_bot_page(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in ANTI_BOT_MARKERS)


def _request_timeout():
    """Return a bounded (connect, read) timeout tuple.

    Keep COLLECTION_TIMEOUT as a compatibility fallback, while allowing production
    to tune connection and response-read budgets independently.
    """
    legacy = float(getattr(settings, "COLLECTION_TIMEOUT", 20))
    connect = float(getattr(settings, "COLLECTION_CONNECT_TIMEOUT", min(4.0, legacy)))
    read = float(getattr(settings, "COLLECTION_READ_TIMEOUT", min(8.0, legacy)))
    return max(0.5, connect), max(1.0, read)


def fetch_html(url: str, force_refresh: bool = False, session_factory=None, sleep_func=None, apply_rate_limit: bool = True) -> FetchResult:
    """Reliable fetch primitive with cache, pacing, retry/backoff and anti-bot detection."""
    started = time.monotonic()
    session_factory = session_factory or requests.Session
    sleep_func = sleep_func or time.sleep
    ttl = int(getattr(settings, "COLLECTION_HTML_CACHE_TTL", 300))
    key = _cache_key(url)
    if not force_refresh and ttl > 0:
        cached = cache.get(key)
        if cached:
            return FetchResult(html=cached, status="cache_hit", attempts=0, from_cache=True, duration_ms=int((time.monotonic() - started) * 1000))

    max_attempts = max(1, int(getattr(settings, "COLLECTION_MAX_ATTEMPTS", 3)))
    backoff_base = float(getattr(settings, "COLLECTION_BACKOFF_BASE", 1.0))
    timeout = _request_timeout()
    session = session_factory()
    session.headers.update(build_headers())

    last_error = ""
    last_status = None
    for attempt in range(1, max_attempts + 1):
        if apply_rate_limit:
            _wait_for_domain_slot(url)
        try:
            response = session.get(url, timeout=timeout, allow_redirects=True)
            last_status = response.status_code
            if response.status_code in TRANSIENT_STATUS_CODES:
                last_error = f"HTTP {response.status_code}"
                if attempt < max_attempts:
                    sleep_func(backoff_base * (3 ** (attempt - 1)))
                    continue
                return FetchResult(None, "transient_failure", last_status, attempt, False, int((time.monotonic() - started) * 1000), last_error)
            if response.status_code >= 400:
                return FetchResult(None, "http_error", last_status, attempt, False, int((time.monotonic() - started) * 1000), f"HTTP {response.status_code}")

            html = _clean_html(response.content, response.encoding)
            if _is_anti_bot_page(html):
                return FetchResult(None, "anti_bot", last_status, attempt, False, int((time.monotonic() - started) * 1000), "Protection anti-bot détectée")
            if ttl > 0:
                cache.set(key, html, timeout=ttl)
            return FetchResult(html, "success", last_status, attempt, False, int((time.monotonic() - started) * 1000))

        except requests.RequestException as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                sleep_func(backoff_base * (3 ** (attempt - 1)))
                continue

    return FetchResult(None, "network_failure", last_status, max_attempts, False, int((time.monotonic() - started) * 1000), last_error)
