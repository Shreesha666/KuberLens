"""
Company Logo Service.
Provides an institutional-grade, local-disk-first logo subsystem.
Checks local persistent disk storage (static/branding/stock_logos/) in < 1ms,
falling back to CDN fetch and deterministic vector monograms.
Supports on-demand write-through disk caching and batch synchronization.
"""
import hashlib
import logging
from pathlib import Path
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
    Manages vector company logos with local-disk-first persistence,
    multi-tier caching, and graceful offline fallback.
    """
    CACHE_KEY_PREFIX = "stock_logo_svg_v2:"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days

    @classmethod
    def get_local_storage_dir(cls) -> Path:
        """
        Returns the persistent directory path for stock logos on disk.
        """
        logo_dir = Path(settings.BASE_DIR) / "static" / "branding" / "stock_logos"
        logo_dir.mkdir(parents=True, exist_ok=True)
        return logo_dir

    @classmethod
    def get_logo(cls, symbol: str) -> tuple[bytes, str]:
        """
        Retrieves the logo for a stock symbol.
        1. Checks persistent local disk storage (< 1ms).
        2. Checks in-memory cache.
        3. Attempts remote CDN fetch with write-through disk persistence.
        4. Generates and persists a clean SVG monogram fallback.
        """
        clean_symbol = symbol.strip().upper()
        logo_dir = cls.get_local_storage_dir()
        cache_key = f"{cls.CACHE_KEY_PREFIX}{clean_symbol}"

        # 1. Local Disk Check (< 1ms instant serve)
        local_svg = logo_dir / f"{clean_symbol}.svg"
        if local_svg.is_file():
            try:
                content = local_svg.read_bytes()
                if content:
                    cache.set(cache_key, content, cls.CACHE_TIMEOUT)
                    return content, "image/svg+xml"
            except OSError as err:
                logger.warning("Could not read local logo file %s: %s", local_svg, err)

        local_png = logo_dir / f"{clean_symbol}.png"
        if local_png.is_file():
            try:
                content = local_png.read_bytes()
                if content:
                    cache.set(cache_key, content, cls.CACHE_TIMEOUT)
                    return content, "image/png"
            except OSError as err:
                logger.warning("Could not read local logo file %s: %s", local_png, err)

        # 2. In-Memory Cache Check
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data, "image/svg+xml"

        # 3. Remote Fetch with Write-Through Disk Persistence
        content, content_type = cls.fetch_remote_logo(clean_symbol)
        if content:
            # Persist to disk for future < 1ms visits
            try:
                ext = "png" if "png" in content_type else "svg"
                save_path = logo_dir / f"{clean_symbol}.{ext}"
                save_path.write_bytes(content)
            except OSError as err:
                logger.error("Could not write logo to disk for %s: %s", clean_symbol, err)

            cache.set(cache_key, content, cls.CACHE_TIMEOUT)
            return content, content_type

        # 4. Deterministic Monogram Fallback & Write-Through Disk Save
        monogram_svg = cls.generate_fallback_monogram(clean_symbol)
        try:
            (logo_dir / f"{clean_symbol}.svg").write_bytes(monogram_svg)
        except OSError as err:
            logger.error("Could not save fallback monogram to disk for %s: %s", clean_symbol, err)

        cache.set(cache_key, monogram_svg, cls.CACHE_TIMEOUT)
        return monogram_svg, "image/svg+xml"

    @classmethod
    def fetch_remote_logo(cls, symbol: str, isin: str = "", timeout: float = 2.5) -> tuple[bytes | None, str]:
        """
        Attempts to fetch the official logo from high-speed vector CDNs and repositories.
        Supports ISIN-based lookups from company-logo.shareperks.in, sibling NSE ticker resolution
        for BSE numeric codes, and direct GitHub/jsDelivr raw vector paths.
        """
        clean_symbol = symbol.strip().upper()
        resolved_isin = isin.strip().upper()
        nse_symbol = None

        # Resolve ISIN and sibling exchange listings if not explicitly provided
        try:
            from apps.instruments.models import ExchangeListing
            listing = (
                ExchangeListing.objects.filter(symbol=clean_symbol)
                .select_related("instrument")
                .first()
            )
            if listing:
                if not resolved_isin and listing.instrument.isin:
                    resolved_isin = listing.instrument.isin.strip().upper()
                if listing.exchange_id == "BSE":
                    nse_sibling = listing.instrument.listings.filter(exchange_id="NSE").first()
                    if nse_sibling and nse_sibling.symbol != clean_symbol:
                        nse_symbol = nse_sibling.symbol.strip().upper()
        except Exception as exc:
            logger.debug("Database listing resolution skipped for %s: %s", clean_symbol, exc)

        candidate_urls = []

        # 1. Primary: Shareperks ISIN CDN (officially co-engineered by Dharun Ashokkumar)
        if resolved_isin:
            candidate_urls.append(f"https://company-logo.shareperks.in/logo/{resolved_isin}/icon.svg")

        # 2. Sibling NSE ticker CDN paths (for BSE numeric scrip codes e.g. 500112 -> SBIN)
        if nse_symbol:
            candidate_urls.extend([
                f"https://cdn.jsdelivr.net/gh/dharunashokkumar/indian-listed-company-logos@main/data/logos/nse/NSE_{nse_symbol}.svg",
                f"https://raw.githubusercontent.com/dharunashokkumar/indian-listed-company-logos/main/data/logos/nse/NSE_{nse_symbol}.svg",
            ])

        # 3. Direct Symbol CDN paths
        candidate_urls.extend([
            f"https://cdn.jsdelivr.net/gh/dharunashokkumar/indian-listed-company-logos@main/data/logos/nse/NSE_{clean_symbol}.svg",
            f"https://raw.githubusercontent.com/dharunashokkumar/indian-listed-company-logos/main/data/logos/nse/NSE_{clean_symbol}.svg",
            f"https://cdn.jsdelivr.net/gh/dharunashokkumar/indian-listed-company-logos@main/data/logos/bse/BSE_{clean_symbol}.svg",
            f"https://raw.githubusercontent.com/dharunashokkumar/indian-listed-company-logos/main/data/logos/bse/BSE_{clean_symbol}.svg",
            f"https://cdn.jsdelivr.net/gh/dharunashokkumar/indian-listed-company-logos@main/data/brand-logos/svg/{clean_symbol}.svg",
            f"https://raw.githubusercontent.com/dharunashokkumar/indian-listed-company-logos/main/data/brand-logos/svg/{clean_symbol}.svg",
        ])

        # 4. Optional Custom / Dharun API Endpoint (if configured)
        api_url = getattr(settings, "DHARUN_LOGO_API_URL", "https://api.dharun.dev/v1/logos")
        if api_url:
            candidate_urls.append(f"{api_url.rstrip('/')}/{clean_symbol}")

        headers = {
            "User-Agent": "KuberLens/2.0 (Mozilla/5.0; StockIntelligence)",
            "Accept": "image/svg+xml,image/*,*/*",
        }
        api_key = getattr(settings, "DHARUN_API_KEY", "")
        if api_key:
            headers["x-api-key"] = api_key

        for url in candidate_urls:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    if response.status == 200:
                        # Check for Shareperks fallback header (skip placeholder SVGs)
                        if response.headers.get("X-Logo-Fallback") == "logo_not_found":
                            continue

                        content = response.read()
                        content_type = response.headers.get("Content-Type", "image/svg+xml")
                        if "svg" in content_type.lower() or content.strip().startswith(b"<svg"):
                            return content, "image/svg+xml"
                        elif "png" in content_type.lower():
                            return content, "image/png"
            except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
                logger.debug("Remote logo lookup failed for %s at %s: %s", clean_symbol, url, exc)
                continue

        return None, ""

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
