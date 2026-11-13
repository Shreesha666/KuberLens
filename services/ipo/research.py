"""
IPO Fundamental Research & Valuation Analysis Engine.
Extracts and computes 3-year CAGR growth, margins, solvency metrics,
and sector peer valuation benchmarking.
"""
from decimal import Decimal
from typing import Any

from apps.ipo.models import IPOFundamentals, IPOMaster


def compute_financial_metrics(fundamentals: IPOFundamentals | None, ipo: IPOMaster) -> dict[str, Any]:
    """
    Computes growth rates, margin analysis, balance sheet ratios, and peer valuation comparisons.
    """
    if not fundamentals:
        return {
            "has_fundamentals": False,
            "cagr_3yr": None,
            "ebitda_margin": None,
            "pat_margin": None,
            "debt_to_equity": None,
            "fresh_issue_ratio": None,
            "ofs_ratio": None,
            "valuation_status": "Valuation Not Available",
            "valuation_badge": "bg-secondary-subtle text-secondary border",
            "peers": [],
        }

    # 1. 3-Year Revenue CAGR Calculation
    cagr = fundamentals.revenue_cagr_3yr
    if cagr is None and fundamentals.revenue_fy_prev2 and fundamentals.revenue_fy_latest:
        p2 = float(fundamentals.revenue_fy_prev2)
        latest = float(fundamentals.revenue_fy_latest)
        if p2 > 0 and latest > 0:
            cagr = Decimal(str(round(((latest / p2) ** 0.5 - 1.0) * 100.0, 2)))

    # 2. Margin Analysis
    ebitda_margin = fundamentals.ebitda_margin_percent
    if ebitda_margin is None and fundamentals.revenue_fy_latest and fundamentals.ebitda_latest:
        rev = fundamentals.revenue_fy_latest
        if rev > Decimal("0.00"):
            ebitda_margin = round((fundamentals.ebitda_latest / rev * Decimal("100.0")), 2)

    pat_margin = fundamentals.pat_margin_percent
    if pat_margin is None and fundamentals.revenue_fy_latest and fundamentals.pat_latest:
        rev = fundamentals.revenue_fy_latest
        if rev > Decimal("0.00"):
            pat_margin = round((fundamentals.pat_latest / rev * Decimal("100.0")), 2)

    # 3. Debt to Equity
    debt_equity = None
    if fundamentals.total_borrowings is not None and fundamentals.net_worth:
        if fundamentals.net_worth > Decimal("0.00"):
            debt_equity = round((fundamentals.total_borrowings / fundamentals.net_worth), 2)

    # 4. Issue Structure Split
    fresh_ratio = Decimal("0.0")
    ofs_ratio = Decimal("0.0")
    if ipo.total_issue_size_cr and ipo.total_issue_size_cr > Decimal("0.00"):
        if ipo.fresh_issue_cr:
            fresh_ratio = round((ipo.fresh_issue_cr / ipo.total_issue_size_cr * Decimal("100.0")), 1)
        if ipo.offer_for_sale_cr:
            ofs_ratio = round((ipo.offer_for_sale_cr / ipo.total_issue_size_cr * Decimal("100.0")), 1)

    # 5. Peer Valuation Comparison
    val_status = "In-Line with Industry"
    val_badge = "bg-primary-subtle text-primary border border-primary-subtle"
    pe_diff_pct = None

    if fundamentals.post_issue_pe and fundamentals.peer_industry_pe and fundamentals.peer_industry_pe > Decimal("0.00"):
        pe_diff = fundamentals.post_issue_pe - fundamentals.peer_industry_pe
        pe_diff_pct = round((pe_diff / fundamentals.peer_industry_pe * Decimal("100.0")), 1)
        if pe_diff_pct <= Decimal("-15.0"):
            val_status = f"Attractive Valuation ({abs(pe_diff_pct)}% Discount to Peers)"
            val_badge = "bg-success-subtle text-success border border-success-subtle"
        elif pe_diff_pct >= Decimal("20.0"):
            val_status = f"Rich Premium ({pe_diff_pct}% Above Peers)"
            val_badge = "bg-warning-subtle text-warning-emphasis border border-warning-subtle"

    return {
        "has_fundamentals": True,
        "cagr_3yr": cagr,
        "ebitda_margin": ebitda_margin,
        "pat_margin": pat_margin,
        "debt_to_equity": debt_equity,
        "fresh_issue_ratio": fresh_ratio,
        "ofs_ratio": ofs_ratio,
        "valuation_status": val_status,
        "valuation_badge": val_badge,
        "pe_diff_percent": pe_diff_pct,
        "peers": fundamentals.peer_comparison_data or [],
    }

