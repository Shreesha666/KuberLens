"""
Fundamental Analysis & Multi-Factor Scoring Engine.
Computes multi-factor scores, evaluates sector-relative valuations, and compiles qualitative drivers.
"""
import logging
from decimal import Decimal

from django.utils import timezone

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Instrument

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:
    CALCULATION_VERSION = "fund-v1.0.0"

    @classmethod
    def evaluate_instrument(
        cls,
        instrument: Instrument,
        raw_data: dict,
        calculation_version: str | None = None,
    ) -> FundamentalSnapshot:
        """
        Evaluates corporate fundamental inputs, derives 5-factor component scores,
        compiles strengths and risk factors, and persists the snapshot.
        """
        version = calculation_version or cls.CALCULATION_VERSION
        positives = []
        negatives = []
        missing = []

        def get_dec(field: str):
            val = raw_data.get(field)
            if val is None or str(val).strip() == "":
                missing.append(field)
                return None
            return Decimal(str(val))

        # 1. Ratios extraction
        pe = get_dec("pe_ratio")
        pb = get_dec("pb_ratio")
        ps = get_dec("ps_ratio")
        ev_ebitda = get_dec("ev_to_ebitda")
        div_yield = get_dec("dividend_yield")
        sector_pe = get_dec("sector_pe") or Decimal("25.0")

        roe = get_dec("roe")
        roce = get_dec("roce")
        op_margin = get_dec("operating_margin")
        net_margin = get_dec("net_profit_margin")
        eps = get_dec("eps")

        de = get_dec("debt_to_equity")
        current_ratio = get_dec("current_ratio")
        interest_cov = get_dec("interest_coverage_ratio")
        fcf = get_dec("free_cash_flow")

        rev_growth = get_dec("revenue_growth_yoy")
        profit_growth = get_dec("profit_growth_yoy")

        promoter = get_dec("promoter_holding")
        fii = get_dec("fii_holding")
        dii = get_dec("dii_holding")
        public = get_dec("public_holding")

        # 2. Valuation Score (0 to 100)
        val_score = 50
        if pe is not None and sector_pe is not None:
            if pe < sector_pe * Decimal("0.8"):
                val_score += 25
                positives.append(f"Attractive valuation: P/E ({pe}) is discounted relative to sector average ({sector_pe}).")
            elif pe > sector_pe * Decimal("1.3"):
                val_score -= 20
                negatives.append(f"Premium valuation: P/E ({pe}) trades significantly above sector benchmark ({sector_pe}).")

        if pb is not None:
            if pb < Decimal("2.0"):
                val_score += 10
            elif pb > Decimal("8.0"):
                val_score -= 10

        if div_yield is not None and div_yield > Decimal("2.5"):
            val_score += 15
            positives.append(f"Solid dividend yield of {div_yield}% provides downside cushion.")

        val_score = max(10, min(95, val_score))

        # 3. Profitability Score (0 to 100)
        prof_score = 50
        if roe is not None:
            if roe >= Decimal("20.0"):
                prof_score += 25
                positives.append(f"Outstanding Return on Equity (ROE: {roe}%).")
            elif roe >= Decimal("14.0"):
                prof_score += 15
            elif roe < Decimal("8.0"):
                prof_score -= 25
                negatives.append(f"Subdued capital productivity: ROE ({roe}%) below corporate cost of capital.")

        if roce is not None and roce >= Decimal("18.0"):
            prof_score += 15
            positives.append(f"Superior Return on Capital Employed (ROCE: {roce}%).")

        if op_margin is not None and op_margin >= Decimal("18.0"):
            prof_score += 10

        prof_score = max(10, min(95, prof_score))

        # 4. Financial Health Score (0 to 100)
        health_score = 50
        if de is not None:
            if de <= Decimal("0.3"):
                health_score += 30
                positives.append(f"Virtually debt-free balance sheet: Debt-to-Equity is {de}.")
            elif de <= Decimal("0.8"):
                health_score += 15
            elif de > Decimal("1.5"):
                health_score -= 30
                negatives.append(f"Elevated financial leverage: Debt-to-Equity ({de}) poses solvency risk.")

        if current_ratio is not None:
            if current_ratio >= Decimal("1.33"):
                health_score += 10
            elif current_ratio < Decimal("1.0"):
                health_score -= 15
                negatives.append(f"Weak liquidity: Current ratio ({current_ratio}) is below 1.0.")

        health_score = max(10, min(95, health_score))

        # 5. Growth Score (0 to 100)
        growth_score = 50
        if rev_growth is not None:
            if rev_growth >= Decimal("15.0"):
                growth_score += 25
                positives.append(f"Strong topline expansion: Revenue YoY growth is {rev_growth}%.")
            elif rev_growth < Decimal("5.0"):
                growth_score -= 15

        if profit_growth is not None:
            if profit_growth >= Decimal("20.0"):
                growth_score += 25
                positives.append(f"Robust net profit acceleration: Profit YoY growth of {profit_growth}%.")
            elif profit_growth < Decimal("0.0"):
                growth_score -= 25
                negatives.append(f"Contracting earnings: Net profit growth is negative ({profit_growth}%).")

        growth_score = max(10, min(95, growth_score))

        # 6. Ownership Score (0 to 100)
        owner_score = 50
        if promoter is not None:
            if promoter >= Decimal("50.0"):
                owner_score += 20
                positives.append(f"High promoter commitment ({promoter}% shareholding).")
            elif promoter < Decimal("30.0"):
                owner_score -= 15

        inst_total = (fii or Decimal("0")) + (dii or Decimal("0"))
        if inst_total >= Decimal("30.0"):
            owner_score += 25
            positives.append(f"Substantial institutional sponsorship (FII + DII holding: {inst_total}%).")

        owner_score = max(10, min(95, owner_score))

        # Overall Weighted Score
        overall = int(
            round(
                (prof_score * 0.25)
                + (growth_score * 0.20)
                + (health_score * 0.20)
                + (val_score * 0.20)
                + (owner_score * 0.15)
            )
        )

        snapshot, _ = FundamentalSnapshot.objects.update_or_create(
            instrument=instrument,
            calculation_version=version,
            defaults={
                "pe_ratio": pe,
                "pb_ratio": pb,
                "ps_ratio": ps,
                "ev_to_ebitda": ev_ebitda,
                "dividend_yield": div_yield,
                "sector_pe": sector_pe,
                "roe": roe,
                "roce": roce,
                "operating_margin": op_margin,
                "net_profit_margin": net_margin,
                "eps": eps,
                "debt_to_equity": de,
                "current_ratio": current_ratio,
                "interest_coverage_ratio": interest_cov,
                "free_cash_flow": fcf,
                "revenue_growth_yoy": rev_growth,
                "profit_growth_yoy": profit_growth,
                "promoter_holding": promoter,
                "fii_holding": fii,
                "dii_holding": dii,
                "public_holding": public,
                "overall_score": overall,
                "growth_score": growth_score,
                "profitability_score": prof_score,
                "valuation_score": val_score,
                "financial_health_score": health_score,
                "ownership_score": owner_score,
                "positive_factors": positives,
                "negative_factors": negatives,
                "missing_fields": missing,
                "calculated_at": timezone.now(),
            },
        )
        return snapshot
