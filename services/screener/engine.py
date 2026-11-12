"""
Stock Screener Domain Engine.
Translates technical, fundamental, and market criteria into filter evaluations
against pre-computed TechnicalIndicatorSnapshot and FundamentalSnapshot tables.
Generates human-readable match explanations and supports system presets.
"""
import csv
import io
import logging
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.screener.models import ScreenerConfiguration, ScreenerResult
from apps.technical_analysis.models import TechnicalIndicatorSnapshot

logger = logging.getLogger(__name__)


SYSTEM_PRESETS = {
    "value": {
        "name": "Deep Value Stocks",
        "description": "Attractive valuation with P/E ≤ 25.0, ROE ≥ 15%, low Debt/Equity ≤ 1.0, and positive quality.",
        "filters": {
            "max_pe": Decimal("25.0"),
            "min_roe": Decimal("15.0"),
            "max_debt_to_equity": Decimal("1.0"),
            "min_score": 50,
        },
    },
    "growth": {
        "name": "High Growth Potential",
        "description": "Companies exhibiting high sales growth (≥15%), profit expansion, and strong return on equity (≥15%).",
        "filters": {
            "min_sales_growth": Decimal("15.0"),
            "min_profit_growth": Decimal("15.0"),
            "min_roe": Decimal("15.0"),
        },
    },
    "quality": {
        "name": "High Quality Moats",
        "description": "Fundamental score ≥ 70, disciplined balance sheet (D/E ≤ 0.8), ROE ≥ 18%, and ROCE ≥ 18%.",
        "filters": {
            "min_score": 70,
            "max_debt_to_equity": Decimal("0.8"),
            "min_roe": Decimal("18.0"),
            "min_roce": Decimal("18.0"),
        },
    },
    "momentum": {
        "name": "Bullish Trend & Momentum",
        "description": "Established technical uptrend, RSI between 55 and 75, and trading above 50-day moving average.",
        "filters": {
            "trend_signal": "BULLISH",
            "min_rsi": Decimal("55.0"),
            "max_rsi": Decimal("75.0"),
            "above_sma50": True,
        },
    },
    "oversold_swing": {
        "name": "Oversold Pullback Candidates",
        "description": "Daily RSI ≤ 40 indicating temporary consolidation/pullback within an active trading universe.",
        "filters": {
            "max_rsi": Decimal("40.0"),
        },
    },
    "large_cap_leaders": {
        "name": "Bluechip Large Cap Universe",
        "description": "Established large-cap market leaders with strong institutional and fundamental foundation.",
        "filters": {
            "market_cap": "LARGE",
            "min_score": 60,
        },
    },
}


class ScreenerEngine:
    @classmethod
    def run_screen(
        cls,
        filters: dict[str, Any],
        configuration: ScreenerConfiguration | None = None,
        save_results: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Executes a screen against the entire active exchange listings universe.
        Returns matched records with human-readable reasons explaining why conditions passed.
        """
        listings = (
            ExchangeListing.objects.filter(is_tradeable=True)
            .select_related("instrument", "exchange")
            .order_by("symbol")
        )

        # Preload latest snapshots in a database-agnostic manner
        latest_quotes: dict[str, MarketQuote] = {}
        for q in MarketQuote.objects.order_by("-retrieved_at"):
            lid = str(q.listing_id)
            if lid not in latest_quotes:
                latest_quotes[lid] = q

        latest_tech: dict[str, TechnicalIndicatorSnapshot] = {}
        for t in TechnicalIndicatorSnapshot.objects.order_by("-timestamp"):
            lid = str(t.listing_id)
            if lid not in latest_tech:
                latest_tech[lid] = t

        latest_fund: dict[str, FundamentalSnapshot] = {}
        for f in FundamentalSnapshot.objects.order_by("-calculated_at"):
            iid = str(f.instrument_id)
            if iid not in latest_fund:
                latest_fund[iid] = f

        matched_results: list[dict[str, Any]] = []
        now = timezone.now()
        audit_records: list[ScreenerResult] = []

        for listing in listings:
            inst = listing.instrument
            quote = latest_quotes.get(str(listing.id))
            tech = latest_tech.get(str(listing.id))
            fund = latest_fund.get(str(inst.id))

            passes = True
            reasons = []

            # 1. Market Cap Filter
            mcap_filter = filters.get("market_cap")
            if mcap_filter:
                if inst.market_cap_category != mcap_filter:
                    passes = False
                else:
                    reasons.append(f"Market Cap: {inst.get_market_cap_category_display()}")

            # 2. Sector Filter
            sector_filter = filters.get("sector")
            if sector_filter:
                if (inst.sector or "").lower() != sector_filter.lower():
                    passes = False
                else:
                    reasons.append(f"Sector: {inst.sector}")

            # 3. Technical: Trend Signal
            trend_filter = filters.get("trend_signal")
            if trend_filter:
                current_trend = tech.trend_signal if tech else "NEUTRAL"
                if current_trend != trend_filter:
                    passes = False
                else:
                    reasons.append(f"Trend: {current_trend}")

            # 4. Technical: RSI Bounds
            min_rsi = filters.get("min_rsi")
            if min_rsi is not None and min_rsi != "":
                val = Decimal(str(min_rsi))
                curr_rsi = tech.rsi_14 if tech and tech.rsi_14 is not None else None
                if curr_rsi is None or curr_rsi < val:
                    passes = False
                else:
                    reasons.append(f"RSI {curr_rsi:.1f} ≥ {val}")

            max_rsi = filters.get("max_rsi")
            if max_rsi is not None and max_rsi != "":
                val = Decimal(str(max_rsi))
                curr_rsi = tech.rsi_14 if tech and tech.rsi_14 is not None else None
                if curr_rsi is None or curr_rsi > val:
                    passes = False
                else:
                    reasons.append(f"RSI {curr_rsi:.1f} ≤ {val}")

            # 5. Technical: Moving Average Alignment
            cur_price = quote.price if quote else (tech.sma_20 if tech else Decimal("0.0"))
            if filters.get("above_sma20"):
                if not tech or not tech.sma_20 or cur_price < tech.sma_20:
                    passes = False
                else:
                    reasons.append(f"Close ₹{cur_price:.2f} > 20 SMA ₹{tech.sma_20:.2f}")

            if filters.get("above_sma50"):
                if not tech or not tech.sma_50 or cur_price < tech.sma_50:
                    passes = False
                else:
                    reasons.append(f"Close ₹{cur_price:.2f} > 50 SMA ₹{tech.sma_50:.2f}")

            if filters.get("above_sma200"):
                if not tech or not tech.sma_200 or cur_price < tech.sma_200:
                    passes = False
                else:
                    reasons.append(f"Close ₹{cur_price:.2f} > 200 SMA ₹{tech.sma_200:.2f}")

            # 6. Fundamental: Score
            min_score = filters.get("min_score")
            if min_score is not None and min_score != "":
                score_val = int(min_score)
                curr_score = fund.overall_score if fund else 0
                if curr_score < score_val:
                    passes = False
                else:
                    reasons.append(f"Score {curr_score} ≥ {score_val}")

            # 7. Fundamental: P/E Ratio
            max_pe = filters.get("max_pe")
            if max_pe is not None and max_pe != "":
                pe_lim = Decimal(str(max_pe))
                curr_pe = fund.pe_ratio if fund and fund.pe_ratio is not None else None
                if curr_pe is None or curr_pe <= 0 or curr_pe > pe_lim:
                    passes = False
                else:
                    reasons.append(f"P/E {curr_pe:.1f} ≤ {pe_lim}")

            min_pe = filters.get("min_pe")
            if min_pe is not None and min_pe != "":
                pe_lim = Decimal(str(min_pe))
                curr_pe = fund.pe_ratio if fund and fund.pe_ratio is not None else None
                if curr_pe is None or curr_pe < pe_lim:
                    passes = False
                else:
                    reasons.append(f"P/E {curr_pe:.1f} ≥ {pe_lim}")

            # 8. Fundamental: ROE & ROCE
            min_roe = filters.get("min_roe")
            if min_roe is not None and min_roe != "":
                roe_lim = Decimal(str(min_roe))
                curr_roe = fund.roe if fund and fund.roe is not None else None
                if curr_roe is None or curr_roe < roe_lim:
                    passes = False
                else:
                    reasons.append(f"ROE {curr_roe:.1f}% ≥ {roe_lim}%")

            min_roce = filters.get("min_roce")
            if min_roce is not None and min_roce != "":
                roce_lim = Decimal(str(min_roce))
                curr_roce = fund.roce if fund and fund.roce is not None else None
                if curr_roce is None or curr_roce < roce_lim:
                    passes = False
                else:
                    reasons.append(f"ROCE {curr_roce:.1f}% ≥ {roce_lim}%")

            # 9. Fundamental: Debt to Equity
            max_de = filters.get("max_debt_to_equity")
            if max_de is not None and max_de != "":
                de_lim = Decimal(str(max_de))
                curr_de = fund.debt_to_equity if fund and fund.debt_to_equity is not None else None
                if curr_de is None or curr_de > de_lim:
                    passes = False
                else:
                    reasons.append(f"Debt/Eq {curr_de:.2f} ≤ {de_lim}")

            # 10. Fundamental: Growth
            min_sales_growth = filters.get("min_sales_growth")
            if min_sales_growth is not None and min_sales_growth != "":
                sg_lim = Decimal(str(min_sales_growth))
                curr_sg = fund.revenue_growth_yoy if fund and fund.revenue_growth_yoy is not None else None
                if curr_sg is None or curr_sg < sg_lim:
                    passes = False
                else:
                    reasons.append(f"Sales Growth {curr_sg:.1f}% ≥ {sg_lim}%")

            if passes:
                cur_price = quote.price if quote else (tech.sma_20 if tech else Decimal("0.0"))
                chg = quote.change if quote else Decimal("0.0")
                chg_pct = quote.change_percent if quote else Decimal("0.0")

                item_data = {
                    "listing": listing,
                    "symbol": listing.symbol,
                    "display_name": inst.display_name,
                    "sector": inst.sector,
                    "market_cap": inst.get_market_cap_category_display(),
                    "price": cur_price,
                    "change": chg,
                    "change_percent": chg_pct,
                    "trend_signal": tech.trend_signal if tech else "NEUTRAL",
                    "rsi": tech.rsi_14 if tech and tech.rsi_14 is not None else None,
                    "overall_score": fund.overall_score if fund else None,
                    "pe_ratio": fund.pe_ratio if fund and fund.pe_ratio is not None else None,
                    "roe": fund.roe if fund and fund.roe is not None else None,
                    "debt_to_equity": fund.debt_to_equity if fund and fund.debt_to_equity is not None else None,
                    "reasons": reasons,
                }
                matched_results.append(item_data)

                if save_results:
                    audit_records.append(
                        ScreenerResult(
                            configuration=configuration,
                            listing=listing,
                            matched_values={
                                "price": str(cur_price),
                                "rsi": str(tech.rsi_14) if tech and tech.rsi_14 is not None else None,
                                "pe": str(fund.pe_ratio) if fund and fund.pe_ratio is not None else None,
                                "roe": str(fund.roe) if fund and fund.roe is not None else None,
                                "score": fund.overall_score if fund else None,
                            },
                            match_reasons=reasons,
                            calculation_version="v1.0",
                            run_timestamp=now,
                        )
                    )

        if save_results and audit_records:
            ScreenerResult.objects.bulk_create(audit_records)

        return matched_results

    @classmethod
    def export_to_csv(cls, results: list[dict[str, Any]]) -> str:
        """
        Exports screener results into CSV string format.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Symbol",
            "Company Name",
            "Sector",
            "Market Cap",
            "Price (INR)",
            "Change (%)",
            "Trend",
            "RSI (14)",
            "Fundamental Score",
            "P/E",
            "ROE (%)",
            "Debt/Equity",
            "Match Reasons",
        ])

        for r in results:
            writer.writerow([
                r["symbol"],
                r["display_name"],
                r["sector"],
                r["market_cap"],
                f"{r['price']:.2f}",
                f"{r['change_percent']:.2f}%",
                r["trend_signal"],
                f"{r['rsi']:.1f}" if r["rsi"] is not None else "-",
                r["overall_score"] if r["overall_score"] is not None else "-",
                f"{r['pe_ratio']:.1f}" if r["pe_ratio"] is not None else "-",
                f"{r['roe']:.1f}%" if r["roe"] is not None else "-",
                f"{r['debt_to_equity']:.2f}" if r["debt_to_equity"] is not None else "-",
                " | ".join(r["reasons"]),
            ])

        return output.getvalue()
