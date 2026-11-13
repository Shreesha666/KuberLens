"""
Multi-IPO Comparison Engine.
Compares 2 to 4 IPOs side-by-side across issue structure, valuation multiples,
financial growth, balance sheet resilience, subscription demand, and 7-pillar quantitative research scores.
Generates an executive analytical narrative highlighting key competitive differentiators.
"""
from decimal import Decimal
from typing import Any

from apps.ipo.models import IPOMaster
from services.ipo.scoring import evaluate_ipo_scoring


def compare_ipos(symbols: list[str]) -> dict[str, Any]:
    """
    Executes a side-by-side comparison for a list of IPO symbols.
    Returns comparison matrix rows, spider radar chart overlay coordinates,
    and an automated comparative narrative.
    """
    cleaned_symbols = [s.strip().upper() for s in symbols if s.strip()][:4]
    if not cleaned_symbols:
        return {"error": "No symbols provided for comparison."}

    ipos = list(
        IPOMaster.objects.filter(symbol__in=cleaned_symbols)
        .select_related("fundamentals", "scoring", "listing")
        .prefetch_related("subscriptions", "documents")
    )

    if not ipos:
        return {"error": "None of the specified IPO symbols were found."}

    # Ensure all IPOs have up-to-date scores
    for ipo in ipos:
        if not hasattr(ipo, "scoring") or ipo.scoring is None:
            evaluate_ipo_scoring(ipo, save=True)
            ipo.refresh_from_db()

    # Sort IPOs in the order of input symbols
    symbol_order = {s: i for i, s in enumerate(cleaned_symbols)}
    ipos.sort(key=lambda x: symbol_order.get(x.symbol, 99))

    # Generate comparison dimensions
    # 1. Basic Metadata
    header_info = []
    for ipo in ipos:
        header_info.append({
            "ipo": ipo,
            "symbol": ipo.symbol,
            "company_name": ipo.company_name,
            "status": ipo.get_status_display(),
            "issue_type": ipo.get_issue_type_display(),
            "sector": ipo.sector,
            "industry": ipo.industry,
            "dates_display": f"{ipo.open_date.strftime('%d %b') if ipo.open_date else 'TBA'} - {ipo.close_date.strftime('%d %b %Y') if ipo.close_date else 'TBA'}",
            "price_band": ipo.price_band_display,
            "lot_size": ipo.lot_size,
            "min_investment": ipo.calculated_min_investment,
            "composite_score": ipo.scoring.composite_score if hasattr(ipo, "scoring") and ipo.scoring else Decimal("0.0"),
            "score_grade": ipo.scoring.score_grade if hasattr(ipo, "scoring") and ipo.scoring else "C",
            "recommendation": ipo.scoring.recommendation if hasattr(ipo, "scoring") and ipo.scoring else "NO_RATING",
            "recommendation_display": ipo.scoring.get_recommendation_display() if hasattr(ipo, "scoring") and ipo.scoring else "No Rating",
            "badge_class": ipo.scoring.recommendation_badge_class if hasattr(ipo, "scoring") and ipo.scoring else "bg-secondary",
        })

    # 2. Structured Comparison Table Rows
    comparison_rows = [
        # Issue Structure
        {
            "category": "Issue Structure",
            "metric": "Total Issue Size",
            "help_text": "Total capital being raised in ₹ Crores",
            "values": [f"₹{ipo.total_issue_size_cr:,.2f} Cr" if ipo.total_issue_size_cr else "TBA" for ipo in ipos],
            "raw_values": [float(ipo.total_issue_size_cr or 0) for ipo in ipos],
            "higher_is_better": None,
        },
        {
            "category": "Issue Structure",
            "metric": "Fresh Issue vs OFS",
            "help_text": "Capital going to company vs exiting shareholders",
            "values": [
                f"Fresh: ₹{ipo.fresh_issue_cr or 0:,.0f} Cr / OFS: ₹{ipo.offer_for_sale_cr or 0:,.0f} Cr"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": None,
        },
        {
            "category": "Issue Structure",
            "metric": "Retail Reservation",
            "help_text": "Mandated retail investor allocation percentage",
            "values": [f"{ipo.retail_quota_percent}%" for ipo in ipos],
            "raw_values": [float(ipo.retail_quota_percent) for ipo in ipos],
            "higher_is_better": True,
        },
        {
            "category": "Issue Structure",
            "metric": "Promoter Holding Post-Issue",
            "help_text": "Promoter skin in the game after public offering",
            "values": [f"{ipo.promoter_holding_post_issue}%" if ipo.promoter_holding_post_issue is not None else "N/A" for ipo in ipos],
            "raw_values": [float(ipo.promoter_holding_post_issue or 0) for ipo in ipos],
            "higher_is_better": True,
        },

        # Valuation Multiples
        {
            "category": "Valuation & Pricing",
            "metric": "Post-Issue P/E",
            "help_text": "Price to Earnings ratio at upper band",
            "values": [
                f"{ipo.fundamentals.post_issue_pe:.1f}x"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.post_issue_pe is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.post_issue_pe) if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.post_issue_pe else 999.0
                for ipo in ipos
            ],
            "higher_is_better": False,  # Lower PE is better
        },
        {
            "category": "Valuation & Pricing",
            "metric": "Peer / Industry P/E",
            "help_text": "Benchmark industry price-to-earnings",
            "values": [
                f"{ipo.fundamentals.peer_industry_pe:.1f}x"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.peer_industry_pe is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": None,
        },

        # Growth & Fundamentals
        {
            "category": "Financial Growth & Quality",
            "metric": "3-Year Revenue CAGR",
            "help_text": "Compounded annual growth rate of top-line revenue",
            "values": [
                f"{ipo.fundamentals.revenue_cagr_3yr:+.1f}%"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.revenue_cagr_3yr is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.revenue_cagr_3yr or 0) if hasattr(ipo, "fundamentals") and ipo.fundamentals else 0.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "Financial Growth & Quality",
            "metric": "Latest FY Revenue",
            "help_text": "Most recent financial year annual revenue",
            "values": [
                f"₹{ipo.fundamentals.revenue_fy_latest:,.2f} Cr"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.revenue_fy_latest is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.revenue_fy_latest or 0) if hasattr(ipo, "fundamentals") and ipo.fundamentals else 0.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "Financial Growth & Quality",
            "metric": "Latest FY PAT",
            "help_text": "Most recent net profit after tax",
            "values": [
                f"₹{ipo.fundamentals.pat_latest:,.2f} Cr"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.pat_latest is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.pat_latest or 0) if hasattr(ipo, "fundamentals") and ipo.fundamentals else -999.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "Financial Growth & Quality",
            "metric": "ROE %",
            "help_text": "Return on Equity",
            "values": [
                f"{ipo.fundamentals.roe_percent:.1f}%"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.roe_percent is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.roe_percent or 0) if hasattr(ipo, "fundamentals") and ipo.fundamentals else 0.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "Financial Growth & Quality",
            "metric": "Debt to Equity Ratio",
            "help_text": "Balance sheet leverage ratio",
            "values": [
                f"{ipo.fundamentals.debt_equity_ratio:.2f}x"
                if hasattr(ipo, "fundamentals") and ipo.fundamentals and ipo.fundamentals.debt_equity_ratio is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.fundamentals.debt_equity_ratio or 0) if hasattr(ipo, "fundamentals") and ipo.fundamentals else 99.0
                for ipo in ipos
            ],
            "higher_is_better": False,
        },

        # Demand & Subscription
        {
            "category": "Demand & Subscription",
            "metric": "Overall Subscription",
            "help_text": "Total issue demand multiple (x)",
            "values": [
                f"{ipo.latest_subscription.total_subscription:.2f}x"
                if getattr(ipo, "latest_subscription", None) and ipo.latest_subscription.total_subscription is not None
                else "Awaiting Bidding"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.latest_subscription.total_subscription) if getattr(ipo, "latest_subscription", None) and ipo.latest_subscription.total_subscription is not None else 0.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "Demand & Subscription",
            "metric": "Retail Subscription",
            "help_text": "RII category demand multiple (x)",
            "values": [
                f"{ipo.latest_subscription.retail_subscription:.2f}x"
                if getattr(ipo, "latest_subscription", None) and ipo.latest_subscription.retail_subscription is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": True,
        },
        {
            "category": "Demand & Subscription",
            "metric": "QIB Institutional Demand",
            "help_text": "Qualified Institutional Buyers subscription multiple",
            "values": [
                f"{ipo.latest_subscription.qib_subscription:.2f}x"
                if getattr(ipo, "latest_subscription", None) and ipo.latest_subscription.qib_subscription is not None
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": True,
        },

        # Research Scores & 7 Pillars
        {
            "category": "7-Pillar Quantitative Scores",
            "metric": "Composite Research Score",
            "help_text": "Weighted multi-pillar aggregate score (out of 100)",
            "values": [
                f"{ipo.scoring.composite_score:.1f} / 100"
                if hasattr(ipo, "scoring") and ipo.scoring
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": [
                float(ipo.scoring.composite_score or 0) if hasattr(ipo, "scoring") and ipo.scoring else 0.0
                for ipo in ipos
            ],
            "higher_is_better": True,
        },
        {
            "category": "7-Pillar Quantitative Scores",
            "metric": "Financial Health & Valuation Pillars",
            "help_text": "Financials (max 20) / Valuation (max 20)",
            "values": [
                f"Fin: {ipo.scoring.financials_score:.0f} / Val: {ipo.scoring.valuation_score:.0f}"
                if hasattr(ipo, "scoring") and ipo.scoring
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": None,
        },
        {
            "category": "7-Pillar Quantitative Scores",
            "metric": "Listing Gain Potential",
            "help_text": "Short-term day-one listing return expectation",
            "values": [
                ipo.scoring.listing_gain_potential
                if hasattr(ipo, "scoring") and ipo.scoring
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": None,
        },
        {
            "category": "7-Pillar Quantitative Scores",
            "metric": "Long-Term Holding Verdict",
            "help_text": "3+ year fundamental accumulation horizon",
            "values": [
                ipo.scoring.long_term_potential
                if hasattr(ipo, "scoring") and ipo.scoring
                else "N/A"
                for ipo in ipos
            ],
            "raw_values": None,
            "higher_is_better": None,
        },
    ]

    # 3. Generate Analytical Narrative Comparison
    # Pick the highest composite score IPO as overall winner
    sorted_by_score = sorted(
        ipos,
        key=lambda x: getattr(x.scoring, "composite_score", Decimal("0.0")) if hasattr(x, "scoring") and x.scoring else Decimal("0.0"),
        reverse=True,
    )
    leader = sorted_by_score[0]
    leader_score = leader.scoring.composite_score if hasattr(leader, "scoring") and leader.scoring else Decimal("0.0")

    insights = []
    if len(ipos) >= 2:
        second = sorted_by_score[1]
        second_score = second.scoring.composite_score if hasattr(second, "scoring") and second.scoring else Decimal("0.0")
        diff = leader_score - second_score
        insights.append(
            f"**{leader.company_name} ({leader.symbol})** leads the comparison with a research score of **{leader_score:.1f}/100**, "
            f"outperforming **{second.company_name} ({second.symbol})** by {diff:.1f} points."
        )

        # Growth comparison
        leader_fund = getattr(leader, "fundamentals", None)
        second_fund = getattr(second, "fundamentals", None)
        if leader_fund and second_fund:
            leader_cagr = leader_fund.revenue_cagr_3yr
            second_cagr = second_fund.revenue_cagr_3yr
            if leader_cagr is not None and second_cagr is not None:
                if leader_cagr > second_cagr:
                    insights.append(
                        f"**Growth Advantage**: {leader.symbol} demonstrates superior top-line expansion with a 3-year revenue CAGR of "
                        f"**{leader_cagr:+.1f}%** vs **{second_cagr:+.1f}%** for {second.symbol}."
                    )
                elif second_cagr > leader_cagr:
                    insights.append(
                        f"**Growth Note**: {second.symbol} delivered faster historical 3-year revenue growth ({second_cagr:+.1f}% vs {leader_cagr:+.1f}%), "
                        f"though {leader.symbol} compensates with higher margin resilience and balance sheet health."
                    )
            elif leader_cagr is not None:
                insights.append(
                    f"**Growth Track Record**: {leader.symbol} delivered historical 3-year revenue CAGR of **{leader_cagr:+.1f}%**."
                )

            # Valuation & Debt comparison
            leader_pe = leader_fund.post_issue_pe
            second_pe = second_fund.post_issue_pe
            if leader_pe is not None and second_pe is not None and leader_pe > 0 and second_pe > 0:
                if leader_pe < second_pe:
                    insights.append(
                        f"**Valuation Comfort**: {leader.symbol} trades at a more conservative multiple of **{leader_pe:.1f}x P/E** "
                        f"compared to {second.symbol}'s **{second_pe:.1f}x P/E**."
                    )
                elif second_pe < leader_pe:
                    insights.append(
                        f"**Valuation Note**: {second.symbol} trades at **{second_pe:.1f}x P/E** vs {leader.symbol}'s **{leader_pe:.1f}x P/E**."
                    )

            leader_de = leader_fund.debt_equity_ratio
            second_de = second_fund.debt_equity_ratio
            if leader_de is not None and second_de is not None:
                if leader_de < second_de:
                    insights.append(
                        f"**Balance Sheet Quality**: {leader.symbol} operates with lower leverage (D/E: **{leader_de:.2f}x** vs **{second_de:.2f}x**)."
                    )
                elif second_de < leader_de:
                    insights.append(
                        f"**Leverage Comparison**: {second.symbol} maintains a cleaner balance sheet (D/E: **{second_de:.2f}x** vs **{leader_de:.2f}x**)."
                    )

    comparison_narrative = "\n\n".join(insights)

    return {
        "ipos": ipos,
        "symbols": [ipo.symbol for ipo in ipos],
        "headers": header_info,
        "rows": comparison_rows,
        "leader": leader,
        "narrative": comparison_narrative,
    }
