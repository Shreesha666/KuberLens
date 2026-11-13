"""
IPO Live Sync Service.
Synchronizes Indian Primary Market data from ipos.markets into IPOMaster
and associated subscription/scoring tables.
"""
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.ipo.models import (
    IPOMaster,
    IPOStatus,
    IPOSubscriptionSnapshot,
    IssueType,
)
from services.ipo.ipos_markets_client import IPOSMarketsClient
from services.ipo.scoring import evaluate_ipo_scoring

logger = logging.getLogger(__name__)


def parse_date(val: Any) -> date | None:
    """Safely parses ISO date string YYYY-MM-DD or datetime into date object."""
    if not val:
        return None
    if isinstance(val, (date, datetime)):
        return val if isinstance(val, date) else val.date()
    val_str = str(val).strip()
    try:
        # Match YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}", val_str):
            return datetime.strptime(val_str[:10], "%Y-%m-%d").date()
    except Exception:
        pass
    return None


def parse_decimal(val: Any, default: Decimal | None = None) -> Decimal | None:
    """Safely converts float/int/str into Decimal."""
    if val is None or val == "":
        return default
    try:
        clean = str(val).replace(",", "").replace("₹", "").replace("Rs.", "").strip()
        return Decimal(clean)
    except (InvalidOperation, ValueError):
        return default


def parse_price_band(band_raw: Any, price_val: Any) -> tuple[Decimal | None, Decimal | None]:
    """Extracts min and max price band from dict, range string, or single price."""
    min_p, max_p = None, None
    if isinstance(band_raw, dict):
        min_p = parse_decimal(band_raw.get("min"))
        max_p = parse_decimal(band_raw.get("max"))
    elif isinstance(band_raw, str):
        # E.g. "Rs.371 to Rs.390" or "63.00 - 67.00" or "25-27.5"
        parts = re.findall(r"\d+(?:\.\d+)?", band_raw)
        if len(parts) >= 2:
            min_p = parse_decimal(parts[0])
            max_p = parse_decimal(parts[1])
        elif len(parts) == 1:
            min_p = max_p = parse_decimal(parts[0])

    if not max_p and price_val:
        price_dec = parse_decimal(price_val)
        max_p = price_dec
        if not min_p:
            min_p = price_dec
    elif not min_p and max_p:
        min_p = max_p

    return min_p, max_p


def map_stage_to_status(stage: str | None, open_d: date | None, close_d: date | None, today: date) -> str:
    """Maps ipos.markets stage string to canonical IPOStatus enum."""
    st = (stage or "").lower().strip()
    if st in ("open", "bidding"):
        return IPOStatus.LIVE
    if st in ("listed", "post_listing"):
        return IPOStatus.LISTED
    if st in ("allotment_finalized", "allotted"):
        return IPOStatus.ALLOTMENT_FINALIZED
    if st in ("closed",):
        return IPOStatus.CLOSED

    # Date-based classification
    if open_d and close_d:
        if open_d <= today <= close_d:
            return IPOStatus.LIVE
        elif close_d < today:
            return IPOStatus.CLOSED
        elif open_d > today:
            return IPOStatus.UPCOMING

    if st in ("upcoming", "drhp_filed", "sebi_observations", "announced"):
        return IPOStatus.UPCOMING

    return IPOStatus.UPCOMING


def generate_fallback_symbol(name: str, slug: str) -> str:
    """Generates clean alphanumeric ticker symbol when exchange symbol is not yet assigned."""
    candidate = ""
    if slug:
        parts = [p.upper() for p in slug.split("-") if p.lower() not in ("limited", "ltd", "india", "services", "technologies")]
        candidate = "".join(parts)[:12]
    if not candidate and name:
        parts = [w.upper() for w in name.split() if w.lower() not in ("limited", "ltd", "india", "pvt")]
        candidate = "".join(parts)[:12]
    clean = re.sub(r"[^A-Z0-9]", "", candidate or "IPO")
    return clean[:12] or "NEWIPO"


def sync_ipos_markets(
    client: IPOSMarketsClient | None = None,
    live_only: bool = False,
    detail_limit: int = 15,
) -> dict[str, int]:
    """
    Synchronizes IPOs from ipos.markets:
    1. Fetches overview.json for active, upcoming, and recent debut listings.
    2. Enriches with granular terms (price band, lot size, subscription) via /data/issue/<slug>.json.
    3. Upserts into IPOMaster and IPOSubscriptionSnapshot.
    """
    if client is None:
        client = IPOSMarketsClient()

    stats = {"created": 0, "updated": 0, "errors": 0}
    today = timezone.now().date()

    overview = client.get_overview()
    if not overview:
        logger.error("Failed to fetch overview.json from ipos.markets")
        return stats

    # Select candidate issues
    candidates: list[dict[str, Any]] = []
    seen_slugs = set()

    for item in overview.get("open", []):
        slug = item.get("slug")
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            candidates.append(item)

    for item in overview.get("upcoming", []):
        slug = item.get("slug")
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            candidates.append(item)

    if not live_only:
        for item in overview.get("recent", []):
            slug = item.get("slug")
            if slug and slug not in seen_slugs:
                seen_slugs.add(slug)
                candidates.append(item)

    # Reconcile existing DB issues that might have legacy mock/seed dates
    known_reconcile_slugs = {
        "NTPCGREEN": "ntpc-green-energy-limited",
        "AFCONS": "afcons-infrastructure-limited",
        "BLACKBUCK": "zinka-logistics-solutions-limited",
        "SWIGGY": "swiggy-limited",
        "WAAREEENER": "waaree-energies-limited",
        "HYUNDAI": "hyundai-motor-india-limited",
    }
    for sym, k_slug in known_reconcile_slugs.items():
        if k_slug not in seen_slugs and IPOMaster.objects.filter(symbol=sym).exists():
            seen_slugs.add(k_slug)
            candidates.append({"slug": k_slug, "symbol": sym})

    logger.info("Found %d candidate IPOs from ipos.markets overview", len(candidates))

    # Process candidates up to detail_limit
    for item in candidates[:detail_limit]:
        slug = item.get("slug")
        if not slug:
            continue

        try:
            detail = client.get_issue_detail(slug) or {}

            # Determine Company Name & Symbol
            company_name = detail.get("display") or item.get("name") or slug.replace("-", " ").title()
            symbol = item.get("symbol") or detail.get("symbols", {}).get("nse") or detail.get("symbol")
            if not symbol:
                symbol = generate_fallback_symbol(company_name, slug)
            symbol = symbol.strip().upper()

            # ISIN
            isin = detail.get("isin")
            if not isin:
                # Deterministic fallback ISIN for unlisted/DRHP issues
                isin = f"INE999{symbol[:6].ljust(6, 'X')}"

            # Dates
            open_d = parse_date(detail.get("open_date") or item.get("open"))
            close_d = parse_date(detail.get("close_date") or item.get("close"))
            listing_d = parse_date(detail.get("listing_date") or item.get("listing"))
            allotment_d = parse_date(detail.get("allotment_date") or detail.get("allotment"))

            # Status
            status = map_stage_to_status(detail.get("stage") or item.get("stage"), open_d, close_d, today)

            # Issue Type (Mainboard vs SME)
            board = (detail.get("board") or item.get("board") or "mainboard").lower()
            issue_type = IssueType.SME if board == "sme" else IssueType.MAINBOARD

            # Prices & Bands
            min_p, max_p = parse_price_band(detail.get("price_band") or item.get("band"), detail.get("issue_price") or item.get("price"))
            issue_price = parse_decimal(detail.get("issue_price") or item.get("price")) or max_p

            # Lot size & min investment
            lot_size = int(detail.get("lot_size") or 1)
            min_investment = Decimal(str(lot_size * (max_p or issue_price or Decimal("100"))))

            # Sizes in Cr
            size_cr = parse_decimal(detail.get("issue_size_cr") or item.get("size"))
            fresh_cr = parse_decimal(detail.get("fresh_issue_cr"), default=Decimal("0.00"))
            ofs_cr = parse_decimal(detail.get("ofs_cr"), default=Decimal("0.00"))

            # Debut Returns
            gain_pct = parse_decimal(detail.get("listing_gain_pct") or item.get("gain"))

            day1_open = None
            if issue_price and gain_pct is not None:
                day1_open = issue_price * (Decimal("1.00") + (gain_pct / Decimal("100.00")))
            elif issue_price:
                day1_open = issue_price

            sector = detail.get("sector") or item.get("sector") or ""
            desc = detail.get("issue_size_desc") or f"{company_name} public issue on {board.upper()}."

            with transaction.atomic():
                ipo_obj, created = IPOMaster.objects.update_or_create(
                    symbol=symbol,
                    defaults={
                        "company_name": company_name,
                        "isin": isin,
                        "issue_type": issue_type,
                        "exchange": "BOTH",
                        "sector": sector[:100],
                        "description": desc,
                        "status": status,
                        "open_date": open_d,
                        "close_date": close_d,
                        "allotment_date": allotment_d,
                        "listing_date": listing_d,
                        "price_band_min": min_p,
                        "price_band_max": max_p,
                        "issue_price": issue_price,
                        "lot_size": lot_size,
                        "min_investment": min_investment,
                        "total_issue_size_cr": size_cr,
                        "fresh_issue_cr": fresh_cr,
                        "offer_for_sale_cr": ofs_cr,
                        "listing_day_open": day1_open,
                        "listing_day_gain_percent": gain_pct,
                    },
                )

                # Process subscription snapshots if present
                sub_data = detail.get("subscription", {})
                latest_sub = sub_data.get("latest", {})
                cats = latest_sub.get("categories", {})

                qib = parse_decimal(cats.get("Qualified Institutional Buyers(QIBs)", {}).get("times"))
                nii = parse_decimal(cats.get("Non Institutional Investors", {}).get("times"))
                retail = parse_decimal(cats.get("Retail Individual Investors(RIIs)", {}).get("times"))
                total_times = parse_decimal(latest_sub.get("total_times") or item.get("sub"))

                if any(x is not None for x in (qib, nii, retail, total_times)):
                    IPOSubscriptionSnapshot.objects.update_or_create(
                        ipo=ipo_obj,
                        day_number=1,
                        defaults={
                            "qib_subscription": qib or Decimal("0.00"),
                            "nii_subscription": nii or Decimal("0.00"),
                            "retail_subscription": retail or Decimal("0.00"),
                            "total_subscription": total_times or Decimal("0.00"),
                        },
                    )

                # Re-compute scoring
                evaluate_ipo_scoring(ipo_obj)

                if created:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1

        except Exception as e:
            logger.exception("Error syncing IPO slug %s: %s", slug, e)
            stats["errors"] += 1

    return stats
