"""
IPO Post-Listing Performance Analytics Service.
Calculates listing day performance, multi-horizon holding returns (1W, 1M, 3M, 6M, 1Y),
maximum drawdowns, current prices from market quotes, and alpha relative to market benchmark.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.ipo.models import IPOMaster, IPOStatus
from apps.market.models import HistoricalCandle, MarketQuote


def get_ipo_current_price(ipo: IPOMaster) -> Decimal:
    """
    Retrieves the most recent market price for an IPO:
    1. Latest MarketQuote for the active ExchangeListing.
    2. Latest HistoricalCandle close price.
    3. listing_day_close recorded at listing.
    4. issue_price fallback.
    """
    if ipo.listing:
        quote = MarketQuote.objects.filter(listing=ipo.listing).order_by("-retrieved_at").first()
        if quote and quote.price > Decimal("0.00"):
            return quote.price

        latest_candle = HistoricalCandle.objects.filter(
            listing=ipo.listing,
            interval="1d",
        ).order_by("-timestamp").first()
        if latest_candle and latest_candle.close > Decimal("0.00"):
            return latest_candle.close

    if ipo.listing_day_close and ipo.listing_day_close > Decimal("0.00"):
        return ipo.listing_day_close

    if ipo.issue_price and ipo.issue_price > Decimal("0.00"):
        return ipo.issue_price

    return Decimal("0.00")


def compute_ipo_performance_metrics(ipo: IPOMaster) -> dict[str, Any]:
    """
    Computes exhaustive post-listing performance metrics for a single IPO:
    - Listing Day Return % & Intraday Range (₹ High - Low)
    - Current Market Price & Total Return since Issue Price %
    - Post-Listing Drift % (Current vs Listing Day Close)
    - Multi-Horizon Returns (1W, 1M, 3M, 6M, 1Y)
    - Maximum Drawdown % from peak price
    - Benchmark relative alpha and performance category classification.
    """
    issue_price = ipo.issue_price or ipo.effective_upper_price or Decimal("0.00")
    listing_open = ipo.listing_day_open or issue_price
    listing_close = ipo.listing_day_close or listing_open
    listing_high = ipo.listing_day_high or max(listing_open, listing_close)
    listing_low = ipo.listing_day_low or min(listing_open, listing_close)

    # 1. Listing Day Gain %
    if ipo.listing_day_gain_percent is not None:
        listing_gain_pct = ipo.listing_day_gain_percent
    elif issue_price > Decimal("0.00") and listing_close > Decimal("0.00"):
        listing_gain_pct = ((listing_close - issue_price) / issue_price) * Decimal("100.0")
    else:
        listing_gain_pct = Decimal("0.00")

    # 2. Current Price & Total Return since Issue Price
    current_price = get_ipo_current_price(ipo)
    if current_price == Decimal("0.00"):
        current_price = listing_close

    if issue_price > Decimal("0.00") and current_price > Decimal("0.00"):
        total_return_pct = ((current_price - issue_price) / issue_price) * Decimal("100.0")
    else:
        total_return_pct = Decimal("0.00")

    # 3. Post-Listing Drift (Return since Day-1 Close)
    if listing_close > Decimal("0.00") and current_price > Decimal("0.00"):
        post_listing_drift_pct = ((current_price - listing_close) / listing_close) * Decimal("100.0")
    else:
        post_listing_drift_pct = Decimal("0.00")

    # 4. Multi-Horizon Returns & Drawdown calculation from historical daily candles
    horizon_returns = {
        "1W": None,
        "1M": None,
        "3M": None,
        "6M": None,
        "1Y": None,
    }
    max_drawdown_pct = Decimal("0.00")
    peak_price = max(listing_high, current_price)

    if ipo.listing:
        candles = list(
            HistoricalCandle.objects.filter(
                listing=ipo.listing,
                interval="1d",
            ).order_by("timestamp")
        )
        if candles:
            latest_close = candles[-1].close
            now = candles[-1].timestamp

            # Max drawdown calculation
            peak = Decimal("0.00")
            max_dd = Decimal("0.00")
            for c in candles:
                if c.high > peak:
                    peak = c.high
                if peak > Decimal("0.00"):
                    dd = ((peak - c.low) / peak) * Decimal("100.0")
                    if dd > max_dd:
                        max_dd = dd
            max_drawdown_pct = round(max_dd, 2)
            peak_price = peak

            # Time horizon returns
            periods = {
                "1W": 7,
                "1M": 30,
                "3M": 90,
                "6M": 180,
                "1Y": 365,
            }
            for horizon_key, days_back in periods.items():
                target_date = now - timedelta(days=days_back)
                # Find candle closest to target_date
                prior_candle = None
                for c in candles:
                    if c.timestamp <= target_date:
                        prior_candle = c
                    else:
                        break
                if prior_candle and prior_candle.close > Decimal("0.00"):
                    ret = ((latest_close - prior_candle.close) / prior_candle.close) * Decimal("100.0")
                    horizon_returns[horizon_key] = round(ret, 2)

    # If no candles exist or new listing, populate initial drift into 1W if listed >= 7 days
    if horizon_returns["1W"] is None and ipo.listing_date:
        days_listed = (timezone.now().date() - ipo.listing_date).days
        if days_listed >= 7 and listing_close > Decimal("0.00"):
            horizon_returns["1W"] = round(post_listing_drift_pct, 2)

    # 5. Benchmark Comparison (Standard benchmark proxy: NIFTY 50 reference ~12% annual / ~1% monthly)
    # Alpha = Total Return - Benchmark Return since listing
    days_since_listing = (timezone.now().date() - (ipo.listing_date or timezone.now().date())).days
    days_since_listing = max(1, days_since_listing)
    benchmark_return_approx = round(Decimal("12.0") * Decimal(days_since_listing) / Decimal("365.0"), 2)
    benchmark_alpha = round(total_return_pct - benchmark_return_approx, 2)

    # 6. Performance Classification & Badge Class
    if total_return_pct >= Decimal("50.0"):
        perf_category = "SUPER_OUTPERFORMER"
        perf_label = "Super Outperformer"
        badge_class = "bg-success text-white"
    elif total_return_pct >= Decimal("15.0"):
        perf_category = "OUTPERFORMER"
        perf_label = "Outperformer"
        badge_class = "bg-success-subtle text-success border border-success-subtle"
    elif total_return_pct >= Decimal("0.0"):
        perf_category = "MARKET_PERFORMER"
        perf_label = "Market Performer"
        badge_class = "bg-info-subtle text-info border border-info-subtle"
    elif total_return_pct >= Decimal("-20.0"):
        perf_category = "UNDERPERFORMER"
        perf_label = "Underperformer"
        badge_class = "bg-warning-subtle text-warning border border-warning-subtle"
    else:
        perf_category = "WEALTH_DESTROYER"
        perf_label = "Wealth Destroyer"
        badge_class = "bg-danger text-white"

    return {
        "ipo": ipo,
        "issue_price": issue_price,
        "listing_day_open": listing_open,
        "listing_day_close": listing_close,
        "listing_day_high": listing_high,
        "listing_day_low": listing_low,
        "listing_day_range": listing_high - listing_low,
        "listing_gain_percent": round(listing_gain_pct, 2),
        "current_price": round(current_price, 2),
        "total_return_percent": round(total_return_pct, 2),
        "post_listing_drift_percent": round(post_listing_drift_pct, 2),
        "peak_price": round(peak_price, 2),
        "max_drawdown_percent": max_drawdown_pct,
        "horizon_returns": horizon_returns,
        "days_since_listing": days_since_listing,
        "benchmark_return_approx": benchmark_return_approx,
        "benchmark_alpha": benchmark_alpha,
        "performance_category": perf_category,
        "performance_label": perf_label,
        "badge_class": badge_class,
    }


def get_listed_ipos_performance_summary(
    issue_type: str | None = None,
    sector: str | None = None,
    sort_by: str = "-total_return",
) -> dict[str, Any]:
    """
    Returns an aggregated summary of all listed IPOs and their computed performance metrics.
    Supports filtering by issue_type (MAINBOARD, SME), sector, and sorting.
    """
    qs = IPOMaster.objects.filter(
        Q(status=IPOStatus.LISTED) | Q(listing_date__isnull=False)
    ).select_related("listing", "fundamentals", "scoring")

    if issue_type and issue_type.upper() != "ALL":
        qs = qs.filter(issue_type=issue_type.upper())

    if sector and sector.upper() != "ALL":
        qs = qs.filter(sector=sector)

    # Compute metric dictionary for each listed IPO
    results: list[dict[str, Any]] = []
    total_listing_gains = Decimal("0.00")
    total_current_returns = Decimal("0.00")
    positive_listing_count = 0
    positive_current_count = 0

    for ipo in qs:
        metrics = compute_ipo_performance_metrics(ipo)
        results.append(metrics)
        total_listing_gains += metrics["listing_gain_percent"]
        total_current_returns += metrics["total_return_percent"]
        if metrics["listing_gain_percent"] > Decimal("0.00"):
            positive_listing_count += 1
        if metrics["total_return_percent"] > Decimal("0.00"):
            positive_current_count += 1

    count = len(results)
    avg_listing_gain = round(total_listing_gains / Decimal(str(count)), 2) if count > 0 else Decimal("0.00")
    avg_current_return = round(total_current_returns / Decimal(str(count)), 2) if count > 0 else Decimal("0.00")
    listing_win_rate = round(Decimal(positive_listing_count) / Decimal(str(count)) * Decimal("100.0"), 1) if count > 0 else Decimal("0.00")
    current_win_rate = round(Decimal(positive_current_count) / Decimal(str(count)) * Decimal("100.0"), 1) if count > 0 else Decimal("0.00")

    # Sorting
    reverse_sort = True
    sort_field = "total_return_percent"
    if sort_by.startswith("-"):
        sort_field = sort_by[1:]
        reverse_sort = True
    elif sort_by.startswith("+"):
        sort_field = sort_by[1:]
        reverse_sort = False
    elif sort_by:
        sort_field = sort_by
        reverse_sort = True

    if sort_field in ["total_return", "total_return_percent"]:
        results.sort(key=lambda x: x["total_return_percent"], reverse=reverse_sort)
    elif sort_field in ["listing_gain", "listing_gain_percent"]:
        results.sort(key=lambda x: x["listing_gain_percent"], reverse=reverse_sort)
    elif sort_field in ["current_price"]:
        results.sort(key=lambda x: x["current_price"], reverse=reverse_sort)
    elif sort_field in ["max_drawdown", "max_drawdown_percent"]:
        results.sort(key=lambda x: x["max_drawdown_percent"], reverse=reverse_sort)
    elif sort_field in ["listing_date"]:
        results.sort(key=lambda x: x["ipo"].listing_date or timezone.now().date(), reverse=reverse_sort)

    top_performers = sorted(results, key=lambda x: x["total_return_percent"], reverse=True)[:5]
    top_listing_gainers = sorted(results, key=lambda x: x["listing_gain_percent"], reverse=True)[:5]

    return {
        "total_listed_count": count,
        "avg_listing_gain": avg_listing_gain,
        "avg_current_return": avg_current_return,
        "listing_win_rate": listing_win_rate,
        "current_win_rate": current_win_rate,
        "positive_listing_count": positive_listing_count,
        "positive_current_count": positive_current_count,
        "top_performers": top_performers,
        "top_listing_gainers": top_listing_gainers,
        "items": results,
    }
