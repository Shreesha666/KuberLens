"""
IPO Quantitative Research Scoring & Recommendation Engine.
Implements the 7-pillar weighted quantitative evaluation model per Section 9 of IPO_research.md:
1. Business Quality & Competitive Moat (20%)
2. Financial Strength & Solvency (20%)
3. Valuation & Price Attractiveness (20%)
4. Growth Trajectory & Scalability (15%)
5. Management Quality & Governance (10%)
6. IPO Structure & Use of Proceeds (10%)
7. Subscription & Market Demand (5%)

Provides transparent factor breakdowns, confidence ratings, data completeness scoring,
and 3-horizon potential evaluations (Listing Day, Short-Term 1-3M, Long-Term 1-3Y).
"""
import math
from decimal import Decimal
from typing import Any

from apps.ipo.models import IPOFundamentals, IPOMaster, IPOScoring
from services.ipo.research import compute_financial_metrics
from services.ipo.subscription import get_subscription_summary

# Standard configurable weights totaling 100% (1.00)
DEFAULT_SCORING_WEIGHTS: dict[str, Decimal] = {
    "business": Decimal("0.20"),      # 20%
    "financials": Decimal("0.20"),    # 20%
    "valuation": Decimal("0.20"),     # 20%
    "growth": Decimal("0.15"),        # 15%
    "governance": Decimal("0.10"),    # 10%
    "structure": Decimal("0.10"),     # 10%
    "demand": Decimal("0.05"),        # 5%
}


def evaluate_ipo_scoring(
    ipo: IPOMaster,
    weights: dict[str, Decimal] | None = None,
    save: bool = True,
) -> dict[str, Any]:
    """
    Computes deterministic multi-pillar scores, horizon evaluations, strengths,
    and risks for an IPO based on RHP data, financials, issue parameters, and demand.
    """
    if weights is None:
        weights = DEFAULT_SCORING_WEIGHTS

    fundamentals: IPOFundamentals | None = getattr(ipo, "fundamentals", None)
    metrics = compute_financial_metrics(fundamentals, ipo)
    sub_summary = get_subscription_summary(ipo)
    latest_gmp = ipo.gmp_records.order_by("-observed_at").first()

    strengths: list[str] = []
    risks: list[str] = []

    # -------------------------------------------------------------
    # 1. Business Quality (Weight: 20%)
    # -------------------------------------------------------------
    b_score = Decimal("70.00")
    if ipo.sector:
        if ipo.sector in ["Utilities", "Technology", "Financial Services", "Capital Goods & Solar"]:
            b_score += Decimal("10.00")
    if ipo.issue_type == "MAINBOARD":
        b_score += Decimal("5.00")

    if fundamentals and fundamentals.key_strengths:
        b_score += Decimal("10.00")
        strengths.append(fundamentals.key_strengths)
    else:
        strengths.append(f"Operating franchise in {ipo.industry or ipo.sector or 'diversified industries'}.")

    business_score = min(Decimal("100.00"), max(Decimal("20.00"), b_score))

    # -------------------------------------------------------------
    # 2. Financial Strength & Solvency (Weight: 20%)
    # -------------------------------------------------------------
    f_score = Decimal("50.00")
    if fundamentals:
        # Profitability check
        if fundamentals.pat_latest is not None:
            if fundamentals.pat_latest > Decimal("0.00"):
                f_score += Decimal("15.00")
                if metrics["pat_margin"] and metrics["pat_margin"] >= Decimal("10.00"):
                    f_score += Decimal("10.00")
                    strengths.append(f"Robust net profit margin of {metrics['pat_margin']:.1f}%.")
            else:
                f_score -= Decimal("20.00")
                risks.append("Currently operating at a net loss on latest audited figures.")

        # Cash flow check
        if fundamentals.cash_flow_operations is not None:
            if fundamentals.cash_flow_operations > Decimal("0.00"):
                f_score += Decimal("10.00")
                strengths.append("Positive cash flow generated from core operations.")
            else:
                f_score -= Decimal("10.00")
                risks.append("Negative operating cash flow requires ongoing external financing.")

        # Solvency / Leverage
        if metrics["debt_to_equity"] is not None:
            de = metrics["debt_to_equity"]
            if de <= Decimal("0.50"):
                f_score += Decimal("15.00")
                strengths.append(f"Conservative balance sheet leverage (Debt/Equity: {de:.2f}x).")
            elif de > Decimal("1.50"):
                f_score -= Decimal("15.00")
                risks.append(f"Elevated balance sheet debt leverage (Debt/Equity: {de:.2f}x).")
    else:
        f_score = Decimal("40.00")
        risks.append("Audited historical financials not yet extracted from prospectus.")

    financials_score = min(Decimal("100.00"), max(Decimal("20.00"), f_score))

    # -------------------------------------------------------------
    # 3. Valuation & Price Attractiveness (Weight: 20%)
    # -------------------------------------------------------------
    v_score = Decimal("65.00")
    if fundamentals and fundamentals.post_issue_pe is not None and fundamentals.peer_industry_pe:
        pe_diff = metrics["pe_diff_percent"]
        if pe_diff is not None:
            if pe_diff <= Decimal("-15.0"):
                v_score = Decimal("90.00")
                strengths.append(f"Priced at an attractive {abs(pe_diff):.1f}% discount to listed industry peers.")
            elif pe_diff <= Decimal("10.0"):
                v_score = Decimal("75.00")
                strengths.append("Pricing is fairly aligned with prevailing industry valuation multiples.")
            elif pe_diff <= Decimal("30.0"):
                v_score = Decimal("55.00")
                risks.append(f"Valuation commands a {pe_diff:.1f}% premium over comparable peers.")
            else:
                v_score = Decimal("35.00")
                risks.append(f"High valuation multiple ({pe_diff:.1f}% above industry benchmarks).")
    elif fundamentals and fundamentals.post_issue_pe is None:
        # Loss-making entity; assess Price to Book
        if fundamentals.post_issue_pb and fundamentals.post_issue_pb <= Decimal("5.00"):
            v_score = Decimal("55.00")
        else:
            v_score = Decimal("40.00")
        risks.append("P/E multiple not applicable due to reported net losses.")
    else:
        v_score = Decimal("50.00")

    valuation_score = min(Decimal("100.00"), max(Decimal("20.00"), v_score))

    # -------------------------------------------------------------
    # 4. Growth Potential (Weight: 15%)
    # -------------------------------------------------------------
    g_score = Decimal("60.00")
    if metrics["cagr_3yr"] is not None:
        cagr = metrics["cagr_3yr"]
        if cagr >= Decimal("40.0"):
            g_score = Decimal("95.00")
            strengths.append(f"Exceptional 3-year revenue CAGR of {cagr:.1f}%.")
        elif cagr >= Decimal("20.0"):
            g_score = Decimal("80.00")
            strengths.append(f"Solid top-line revenue CAGR of {cagr:.1f}%.")
        elif cagr >= Decimal("10.0"):
            g_score = Decimal("65.00")
        elif cagr > Decimal("0.0"):
            g_score = Decimal("50.00")
        else:
            g_score = Decimal("35.00")
            risks.append("Stagnant or contracting revenue trajectory.")
    else:
        g_score = Decimal("50.00")

    growth_score = min(Decimal("100.00"), max(Decimal("20.00"), g_score))

    # -------------------------------------------------------------
    # 5. Management & Governance (Weight: 10%)
    # -------------------------------------------------------------
    gov_score = Decimal("75.00")
    # Promoter post-issue stake
    if ipo.promoter_holding_post_issue is not None:
        if ipo.promoter_holding_post_issue >= Decimal("55.00"):
            gov_score += Decimal("10.00")
            strengths.append(f"High promoter skin-in-the-game retained post-issue ({ipo.promoter_holding_post_issue:.1f}%).")
        elif ipo.promoter_holding_post_issue < Decimal("25.00") and ipo.promoter_holding_post_issue > Decimal("0.00"):
            gov_score -= Decimal("15.00")
            risks.append("Substantial post-issue promoter dilution below 25%.")

    # Lead manager quality
    if ipo.lead_managers:
        tier1_managers = ["Kotak", "Axis", "Citigroup", "Morgan Stanley", "Jefferies", "BofA", "SBI Capital", "ICICI"]
        if any(mgr in ipo.lead_managers for mgr in tier1_managers):
            gov_score += Decimal("10.00")

    governance_score = min(Decimal("100.00"), max(Decimal("20.00"), gov_score))

    # -------------------------------------------------------------
    # 6. IPO Structure & Use of Proceeds (Weight: 10%)
    # -------------------------------------------------------------
    s_score = Decimal("60.00")
    fresh_ratio = metrics["fresh_issue_ratio"]
    if fresh_ratio is not None:
        if fresh_ratio >= Decimal("75.00"):
            s_score = Decimal("90.00")
            strengths.append(f"Favorable structure: {fresh_ratio:.0f}% fresh capital invested directly into corporate growth.")
        elif fresh_ratio >= Decimal("40.00"):
            s_score = Decimal("75.00")
        elif fresh_ratio > Decimal("0.00"):
            s_score = Decimal("55.00")
            risks.append(f"Majority OFS offer ({metrics['ofs_ratio']:.0f}%) with limited fresh proceeds.")
        else:
            s_score = Decimal("40.00")
            risks.append("100% Offer for Sale (OFS): complete promoter/investor liquidity exit with zero growth capital.")

    if fundamentals and fundamentals.use_of_proceeds:
        if "debt repayment" in fundamentals.use_of_proceeds.lower() or "capex" in fundamentals.use_of_proceeds.lower() or "expansion" in fundamentals.use_of_proceeds.lower():
            s_score += Decimal("5.00")

    structure_score = min(Decimal("100.00"), max(Decimal("20.00"), s_score))

    # -------------------------------------------------------------
    # 7. Subscription & Market Demand (Weight: 5%)
    # -------------------------------------------------------------
    d_score = Decimal("65.00")
    if sub_summary["has_data"] and sub_summary["latest"]:
        total_sub = sub_summary["latest"].total_subscription
        if total_sub >= Decimal("20.00"):
            d_score = Decimal("95.00")
            strengths.append(f"Intense bidding demand across categories ({total_sub:.1f}x subscribed).")
        elif total_sub >= Decimal("3.00"):
            d_score = Decimal("80.00")
            strengths.append(f"Comfortably oversubscribed at {total_sub:.1f}x.")
        elif total_sub >= Decimal("1.00"):
            d_score = Decimal("70.00")
        else:
            d_score = Decimal("45.00")
            risks.append(f"Muted initial demand multiple ({total_sub:.2f}x).")

    if latest_gmp and latest_gmp.reported_gmp:
        if latest_gmp.estimated_gain_percent and latest_gmp.estimated_gain_percent >= Decimal("30.0"):
            d_score = min(Decimal("100.00"), d_score + Decimal("5.00"))
        elif latest_gmp.reported_gmp < Decimal("0.00"):
            d_score = max(Decimal("20.00"), d_score - Decimal("15.00"))
            risks.append("Grey market premium is trading at a discount.")

    demand_score = min(Decimal("100.00"), max(Decimal("20.00"), d_score))

    # Add general prospectus risk if provided
    if fundamentals and fundamentals.key_risks and fundamentals.key_risks not in risks:
        risks.append(fundamentals.key_risks)

    # -------------------------------------------------------------
    # Weighted Overall Score & Data Completeness
    # -------------------------------------------------------------
    overall = (
        (business_score * weights["business"]) +
        (financials_score * weights["financials"]) +
        (valuation_score * weights["valuation"]) +
        (growth_score * weights["growth"]) +
        (governance_score * weights["governance"]) +
        (structure_score * weights["structure"]) +
        (demand_score * weights["demand"])
    )
    overall_score = round(overall, 2)

    # Data Completeness Calculation
    fields_checked = [
        fundamentals is not None,
        fundamentals and fundamentals.revenue_fy_latest is not None,
        fundamentals and fundamentals.ebitda_latest is not None,
        fundamentals and fundamentals.pat_latest is not None,
        fundamentals and fundamentals.net_worth is not None,
        fundamentals and fundamentals.total_borrowings is not None,
        bool(ipo.lead_managers),
        bool(ipo.lot_size),
        bool(ipo.total_issue_size_cr),
        sub_summary["has_data"],
    ]
    completeness = Decimal(str(round((sum(1 for f in fields_checked if f) / len(fields_checked)) * 100.0, 1)))

    # Confidence Level
    if completeness >= Decimal("80.0"):
        confidence = "HIGH"
    elif completeness >= Decimal("50.0"):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    # Recommendation Classification
    if completeness < Decimal("40.0"):
        recommendation = "INSUFFICIENT_DATA"
        rationale = "Core financial disclosures and regulatory parameters are not yet fully available."
    elif overall_score >= Decimal("80.00"):
        recommendation = "STRONG_RESEARCH_CANDIDATE"
        rationale = f"{ipo.company_name} demonstrates resilient fundamental metrics, robust growth, and reasonable pricing relative to peer benchmarks."
    elif overall_score >= Decimal("65.00"):
        recommendation = "CONSIDER_APPLYING"
        rationale = f"{ipo.company_name} displays healthy operational metrics with balanced risk-reward parameters."
    elif overall_score >= Decimal("50.00"):
        recommendation = "APPLY_WITH_CAUTION"
        rationale = f"{ipo.company_name} presents selective valuation or leverage risks warranting disciplined sizing."
    else:
        recommendation = "AVOID"
        rationale = f"{ipo.company_name} carries significant fundamental headwinds, steep pricing, or high OFS dilution."

    # Horizon Evaluations
    # 1. Listing Gain Potential
    if demand_score >= Decimal("75.00") and overall_score >= Decimal("72.00"):
        listing_potential = "HIGH"
    elif demand_score >= Decimal("60.00") or overall_score >= Decimal("60.00"):
        listing_potential = "MODERATE"
    else:
        listing_potential = "LOW"

    # 2. Short-Term Investment Potential (1-3 Months)
    if growth_score >= Decimal("70.00") and valuation_score >= Decimal("60.00") and overall_score >= Decimal("68.00"):
        short_term_potential = "POSITIVE"
    elif overall_score >= Decimal("55.00"):
        short_term_potential = "NEUTRAL"
    else:
        short_term_potential = "CAUTION"

    # 3. Long-Term Investment Potential (1-3 Years)
    if business_score >= Decimal("75.00") and financials_score >= Decimal("65.00") and governance_score >= Decimal("70.00") and overall_score >= Decimal("70.00"):
        long_term_potential = "POSITIVE"
    elif overall_score >= Decimal("55.00"):
        long_term_potential = "NEUTRAL"
    else:
        long_term_potential = "CAUTION"

    # Deduplicate strengths and risks
    unique_strengths = list(dict.fromkeys(strengths))[:5]
    unique_risks = list(dict.fromkeys(risks))[:5]

    result = {
        "business_score": business_score,
        "financials_score": financials_score,
        "valuation_score": valuation_score,
        "growth_score": growth_score,
        "governance_score": governance_score,
        "structure_score": structure_score,
        "demand_score": demand_score,
        "overall_score": overall_score,
        "recommendation": recommendation,
        "listing_gain_potential": listing_potential,
        "short_term_potential": short_term_potential,
        "long_term_potential": long_term_potential,
        "confidence_level": confidence,
        "data_completeness_percent": completeness,
        "scoring_rationale": rationale,
        "strengths_list": unique_strengths,
        "risks_list": unique_risks,
        "weights": weights,
    }

    if save:
        IPOScoring.objects.update_or_create(
            ipo=ipo,
            defaults={
                "business_score": business_score,
                "financials_score": financials_score,
                "valuation_score": valuation_score,
                "growth_score": growth_score,
                "governance_score": governance_score,
                "structure_score": structure_score,
                "demand_score": demand_score,
                "overall_score": overall_score,
                "recommendation": recommendation,
                "listing_gain_potential": listing_potential,
                "short_term_potential": short_term_potential,
                "long_term_potential": long_term_potential,
                "confidence_level": confidence,
                "data_completeness_percent": completeness,
                "scoring_rationale": rationale,
                "strengths_list": unique_strengths,
                "risks_list": unique_risks,
            },
        )

    return result


def get_radar_chart_geometry(scoring: IPOScoring) -> dict[str, Any]:
    """
    Computes mathematical coordinates for a 7-pillar SVG spider/radar chart.
    Returns SVG concentric grid polygon points, axis lines, and data polygon string.
    """
    cx, cy, r = 160.0, 140.0, 95.0
    pillars = [
        ("Business Quality", float(scoring.business_score)),
        ("Financial Health", float(scoring.financials_score)),
        ("Valuation", float(scoring.valuation_score)),
        ("Growth", float(scoring.growth_score)),
        ("Governance", float(scoring.governance_score)),
        ("Structure", float(scoring.structure_score)),
        ("Demand", float(scoring.demand_score)),
    ]
    n = len(pillars)
    grid_polygons = []
    for level in [0.25, 0.50, 0.75, 1.0]:
        pts = []
        for i in range(n):
            angle = -math.pi / 2.0 + (2.0 * math.pi * i) / n
            x = cx + r * level * math.cos(angle)
            y = cy + r * level * math.sin(angle)
            pts.append(f"{x:.1f},{y:.1f}")
        grid_polygons.append(" ".join(pts))

    axes = []
    data_pts = []
    for i, (name, val) in enumerate(pillars):
        angle = -math.pi / 2.0 + (2.0 * math.pi * i) / n
        x_outer = cx + r * math.cos(angle)
        y_outer = cy + r * math.sin(angle)
        x_label = cx + (r + 26.0) * math.cos(angle)
        y_label = cy + (r + 14.0) * math.sin(angle)

        axes.append({
            "name": name,
            "x_outer": round(x_outer, 1),
            "y_outer": round(y_outer, 1),
            "x_label": round(x_label, 1),
            "y_label": round(y_label, 1),
            "val": int(round(val)),
        })
        clamped_val = max(10.0, min(100.0, val))
        x_data = cx + r * (clamped_val / 100.0) * math.cos(angle)
        y_data = cy + r * (clamped_val / 100.0) * math.sin(angle)
        data_pts.append(f"{x_data:.1f},{y_data:.1f}")

    return {
        "grid_polygons": grid_polygons,
        "axes": axes,
        "data_polygon": " ".join(data_pts),
    }
