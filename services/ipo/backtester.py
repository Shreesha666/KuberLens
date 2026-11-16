"""
IPO Strategy Backtesting Engine.
Simulates historical listing-day outcomes and capital growth based on customizable
quantitative filters: Grey Market Premium (GMP), QIB Subscription Multiples,
Retail Demand, Issue Size, and Board Classification.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.ipo.models import IPOMaster, IPOStatus


def run_ipo_backtest(
    min_gmp_percent: Decimal | None = None,
    min_qib_sub: Decimal | None = None,
    min_retail_sub: Decimal | None = None,
    issue_type: str = "ALL",
    min_issue_size_cr: Decimal | None = None,
    months: int | None = None,
    initial_capital: Decimal = Decimal("100000.00"),
    lot_capital: Decimal = Decimal("15000.00"),
) -> dict[str, Any]:
    """
    Executes a historical strategy simulation across listed Indian IPOs.
    """
    qs = IPOMaster.objects.filter(
        status=IPOStatus.LISTED,
    ).select_related("listing").prefetch_related("subscriptions", "gmp_records")

    if issue_type and issue_type.upper() in ["MAINBOARD", "SME"]:
        qs = qs.filter(issue_type=issue_type.upper())

    if min_issue_size_cr is not None and min_issue_size_cr > Decimal("0.00"):
        qs = qs.filter(total_issue_size_cr__gte=min_issue_size_cr)

    if months is not None and months > 0:
        cutoff_date = timezone.now().date() - timedelta(days=months * 30)
        qs = qs.filter(listing_date__gte=cutoff_date)

    # Order chronologically for realistic simulation
    all_listed = list(qs.order_by("listing_date", "open_date"))
    total_in_universe = len(all_listed)

    matched_trades = []
    current_capital = initial_capital
    cumulative_pnl = Decimal("0.00")
    winning_count = 0
    losing_count = 0

    equity_curve = [
        {
            "step": 0,
            "date": "Start",
            "symbol": "START",
            "company_name": "Initial Portfolio",
            "capital": float(initial_capital),
            "pnl": 0.0,
            "gain_percent": 0.0,
        }
    ]

    for ipo in all_listed:
        # 1. Evaluate Subscription Filters
        sub = ipo.subscriptions.order_by("-day_number").first()
        qib_val = sub.qib_subscription if sub else Decimal("0.00")
        retail_val = sub.retail_subscription if sub else Decimal("0.00")

        if min_qib_sub is not None and qib_val < min_qib_sub:
            continue
        if min_retail_sub is not None and retail_val < min_retail_sub:
            continue

        # 2. Evaluate GMP Filter
        gmp_record = ipo.gmp_records.order_by("-observed_at").first()
        gmp_val = gmp_record.estimated_gain_percent if (gmp_record and gmp_record.estimated_gain_percent is not None) else None
        if min_gmp_percent is not None:
            if gmp_val is None or gmp_val < min_gmp_percent:
                continue

        # 3. Determine Listing Return
        listing_gain = ipo.listing_day_gain_percent
        listing_price = ipo.listing_day_close or ipo.listing_day_open or ipo.effective_upper_price
        issue_price = ipo.effective_upper_price

        if listing_gain is None:
            if ipo.listing and ipo.listing.last_price and issue_price > Decimal("0.00"):
                listing_price = ipo.listing.last_price
                listing_gain = round(((listing_price - issue_price) / issue_price) * Decimal("100.00"), 2)
            else:
                continue

        trade_pnl = round(lot_capital * (listing_gain / Decimal("100.00")), 2)
        cumulative_pnl += trade_pnl
        current_capital += trade_pnl

        if listing_gain >= Decimal("0.00"):
            winning_count += 1
        else:
            losing_count += 1

        trade_info = {
            "ipo": ipo,
            "symbol": ipo.symbol,
            "company_name": ipo.company_name,
            "listing_date": ipo.listing_date,
            "issue_type": ipo.issue_type,
            "issue_price": issue_price,
            "listing_price": listing_price,
            "listing_gain_percent": listing_gain,
            "pnl": trade_pnl,
            "capital_after": current_capital,
            "qib_subscription": qib_val,
            "retail_subscription": retail_val,
            "gmp_percent": gmp_val,
            "is_win": listing_gain >= Decimal("0.00"),
        }
        matched_trades.append(trade_info)

        equity_curve.append({
            "step": len(matched_trades),
            "date": ipo.listing_date.strftime("%d %b %Y") if ipo.listing_date else f"IPO #{len(matched_trades)}",
            "symbol": ipo.symbol,
            "company_name": ipo.company_name,
            "capital": float(current_capital),
            "pnl": float(trade_pnl),
            "gain_percent": float(listing_gain),
        })

    total_matched = len(matched_trades)
    win_rate = round((Decimal(winning_count) / Decimal(total_matched) * Decimal("100.00")), 1) if total_matched > 0 else Decimal("0.00")

    if total_matched > 0:
        gains = [t["listing_gain_percent"] for t in matched_trades]
        avg_gain = round(sum(gains) / Decimal(total_matched), 1)
        max_gain = max(gains)
        max_loss = min(gains)
    else:
        avg_gain = Decimal("0.00")
        max_gain = Decimal("0.00")
        max_loss = Decimal("0.00")

    total_return_percent = round(((current_capital - initial_capital) / initial_capital) * Decimal("100.00"), 1)

    return {
        "total_in_universe": total_in_universe,
        "total_matched": total_matched,
        "winning_count": winning_count,
        "losing_count": losing_count,
        "win_rate": win_rate,
        "avg_gain": avg_gain,
        "max_gain": max_gain,
        "max_loss": max_loss,
        "initial_capital": initial_capital,
        "lot_capital": lot_capital,
        "final_capital": current_capital,
        "total_pnl": cumulative_pnl,
        "total_return_percent": total_return_percent,
        "trades": matched_trades,
        "equity_curve": equity_curve,
        "filters": {
            "min_gmp_percent": min_gmp_percent,
            "min_qib_sub": min_qib_sub,
            "min_retail_sub": min_retail_sub,
            "issue_type": issue_type,
            "min_issue_size_cr": min_issue_size_cr,
            "months": months,
        },
    }
