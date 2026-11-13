"""
Company Logo Service.
Fetches, caches, and proxies vector company logos from api.dharun.dev with local caching
and deterministic SVG monogram fallbacks for offline resilience.
"""
import hashlib
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Palette of modern, professional brand colors for monogram fallbacks
MONOGRAM_PALETTE = [
    "#2563EB",  # Royal Blue
    "#059669",  # Emerald Green
    "#D97706",  # Amber
    "#7C3AED",  # Violet
    "#DC2626",  # Crimson
    "#0891B2",  # Cyan
    "#4F46E5",  # Indigo
    "#0D9488",  # Teal
    "#BE185D",  # Rose
    "#4338CA",  # Dark Indigo
]


class CompanyLogoService:
    """
    Manages vector company logos with multi-tier caching and graceful offline fallback.
    """
    CACHE_KEY_PREFIX = "stock_logo_svg_v1:"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days for live logos
    FALLBACK_CACHE_TIMEOUT = 60 * 60 * 1  # 1 hour for fallbacks

    @classmethod
    def get_logo(cls, symbol: str) -> tuple[bytes, str]:
        """
        Retrieves the SVG logo for a stock symbol.
        Returns a tuple of (content_bytes, content_type).
        """
        clean_symbol = symbol.strip().upper()
        cache_key = f"{cls.CACHE_KEY_PREFIX}{clean_symbol}"

        # 1. Check local cache (distinguishing official logo from fallback monogram)
        cached_data = cache.get(cache_key)
        is_cached_monogram = bool(
            cached_data and b'letter-spacing="0.5"' in cached_data
        )
        if cached_data and not is_cached_monogram:
            return cached_data, "image/svg+xml"

        # 2. Attempt fetching from CDN and API sources
        candidate_urls = [
            f"https://cdn.jsdelivr.net/gh/MrChartist/global-stock-logos@main/logos/{clean_symbol}.svg",
            f"https://raw.githubusercontent.com/MrChartist/global-stock-logos/main/logos/{clean_symbol}.svg",
        ]
        api_url = getattr(settings, "DHARUN_LOGO_API_URL", "https://api.dharun.dev/v1/logos")
        if api_url:
            candidate_urls.append(f"{api_url.rstrip('/')}/{clean_symbol}")

        api_key = getattr(settings, "DHARUN_API_KEY", "")
        headers = {
            "User-Agent": "KuberLens/1.0 (Mozilla/5.0)",
            "Accept": "image/svg+xml,image/*,*/*",
        }
        if api_key:
            headers["x-api-key"] = api_key

        for url in candidate_urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=3.0) as response:
                    if response.status == 200:
                        content = response.read()
                        content_type = response.headers.get("Content-Type", "image/svg+xml")
                        if "svg" in content_type.lower() or content.strip().startswith(b"<svg"):
                            cache.set(cache_key, content, cls.CACHE_TIMEOUT)
                            return content, "image/svg+xml"
                        elif "png" in content_type.lower():
                            cache.set(cache_key, content, cls.CACHE_TIMEOUT)
                            return content, "image/png"
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                logger.debug("Could not fetch remote logo for %s from %s: %s", clean_symbol, url, exc)
                continue

        # If previous fallback was cached and remote failed, reuse cached fallback
        if cached_data:
            return cached_data, "image/svg+xml"

        # 3. Deterministic SVG Monogram Fallback
        fallback_svg = cls.generate_fallback_monogram(clean_symbol)
        cache.set(cache_key, fallback_svg, cls.FALLBACK_CACHE_TIMEOUT)
        return fallback_svg, "image/svg+xml"

    @classmethod
    def generate_fallback_monogram(cls, symbol: str) -> bytes:
        """
        Generates a clean, modern SVG monogram badge for stocks without a brand logo
        or when offline. Deterministically picks a color based on the symbol's hash.
        """
        clean_symbol = symbol.strip().upper()
        initials = clean_symbol[:3] if len(clean_symbol) <= 4 else clean_symbol[:2]

        # Deterministic color selection
        hash_val = int(hashlib.md5(clean_symbol.encode("utf-8")).hexdigest(), 16)
        bg_color = MONOGRAM_PALETTE[hash_val % len(MONOGRAM_PALETTE)]

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48">
  <rect width="48" height="48" rx="10" fill="{bg_color}"/>
  <text x="50%" y="54%" font-family="system-ui, -apple-system, sans-serif" font-size="15" font-weight="700" fill="#ffffff" text-anchor="middle" dominant-baseline="middle" letter-spacing="0.5">{initials}</text>
</svg>"""
        return svg.encode("utf-8")
