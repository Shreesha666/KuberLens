"""
Dual-Perspective Recommendation Evaluator.
Distinguishes strategy guidance for Existing Holders versus New Prospective Investors.
Strictly prohibits irresponsible averaging down recommendations on deteriorating fundamentals.
"""
from decimal import Decimal
from typing import Any

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import ExchangeListing
from apps.technical_analysis.models import TechnicalIndicatorSnapshot


class RecommendationEvaluator:
    @classmethod
    def evaluate(
        cls,
        listing: ExchangeListing,
        holding: Holding | None = None,
        technical: TechnicalIndicatorSnapshot | None = None,
        fundamental: FundamentalSnapshot | None = None,
        portfolio_total_value: Decimal | None = None,
    ) -> dict[str, Any]:
        """
        Generates distinct recommendations for:
        1. Existing Holders (capital preservation, trim, accumulate, stop loss)
        2. New Prospective Investors (entry triggers, invalidation, price targets)
        """
        current_price = holding.current_price if holding else Decimal("1000.0")
        if not holding and technical and technical.bollinger_middle:
            current_price = technical.bollinger_middle

        # ------------------------------------------------------------------
        # 1. Existing Holder Guidance
        # ------------------------------------------------------------------
        holder_rec = {
            "is_holder": False,
            "action": "N/A",
            "existing_avg_price": None,
            "quantity": 0,
            "allocation_pct": Decimal("0.0"),
            "unrealised_pnl": Decimal("0.0"),
            "unrealised_pct": Decimal("0.0"),
            "reasoning": "You do not currently hold an open position in this stock.",
            "invalidation_condition": "None",
            "warning": None,
        }

        if holding and holding.total_quantity > 0:
            holder_rec["is_holder"] = True
            holder_rec["existing_avg_price"] = holding.average_buy_price
            holder_rec["quantity"] = holding.total_quantity
            holder_rec["unrealised_pnl"] = holding.unrealised_pnl
            holder_rec["unrealised_pct"] = holding.unrealised_pnl_percent

            alloc_pct = Decimal("0.0")
            if portfolio_total_value and portfolio_total_value > Decimal("0.00"):
                alloc_pct = round((holding.current_value / portfolio_total_value) * Decimal("100.0"), 2)
            holder_rec["allocation_pct"] = alloc_pct

            # Action determination rules
            trend = technical.trend_signal if technical else "NEUTRAL"
            rsi_val = float(technical.rsi_14) if technical and technical.rsi_14 else 50.0
            fund_score = fundamental.overall_score if fundamental else 50
            unrealised = holding.unrealised_pnl_percent

            if unrealised >= Decimal("30.0"):
                holder_rec["action"] = "PARTIAL PROFIT BOOKING"
                holder_rec["reasoning"] = (
                    f"Substantial unrealised gain (+{unrealised}%). "
                    "Consider trimming 20-30% of position to lock in capital gains."
                )
                holder_rec["invalidation_condition"] = "Trailing stop below 20-day EMA."

            elif alloc_pct >= Decimal("20.0"):
                holder_rec["action"] = "REDUCE EXPOSURE"
                holder_rec["reasoning"] = (
                    f"Concentration risk: this stock occupies {alloc_pct}% of total portfolio value. "
                    "Trim toward the 10-12% target exposure."
                )
                holder_rec["invalidation_condition"] = "Portfolio rebalancing ceiling reached."

            elif trend == "BEARISH" and unrealised <= Decimal("-12.0"):
                holder_rec["action"] = "EXIT"
                holder_rec["reasoning"] = (
                    "Position in technical downtrend below major moving averages with >12% loss. "
                    "Preserve remaining capital."
                )
                holder_rec["invalidation_condition"] = "Breakdown below major structural support."
                if fund_score < 45:
                    holder_rec["warning"] = "DO NOT AVERAGE DOWN: Deteriorating corporate fundamentals confirm structural risk."

            elif trend == "BULLISH" and fund_score >= 65 and alloc_pct < Decimal("10.0"):
                holder_rec["action"] = "ADD / ACCUMULATE"
                holder_rec["reasoning"] = (
                    f"High fundamental quality ({fund_score}/100) and bullish technical trend. "
                    "Room exists within portfolio allocation limit to add on support pullbacks."
                )
                holder_rec["invalidation_condition"] = "Close below 50-day moving average."

            elif rsi_val >= 75.0:
                holder_rec["action"] = "HOLD / TIGHTEN STOP"
                holder_rec["reasoning"] = "Stock is overbought (RSI > 75). Hold position but trail stops closely."
                holder_rec["invalidation_condition"] = "Daily close below prior 3-day low."

            else:
                holder_rec["action"] = "HOLD"
                holder_rec["reasoning"] = "Investment thesis intact. Maintain current position weight."
                holder_rec["invalidation_condition"] = "Daily close below 200 SMA."

        # ------------------------------------------------------------------
        # 2. New Investor Guidance
        # ------------------------------------------------------------------
        tech_trend = technical.trend_signal if technical else "NEUTRAL"
        support = technical.support_level if technical and technical.support_level else (current_price * Decimal("0.95"))
        resistance = technical.resistance_level if technical and technical.resistance_level else (current_price * Decimal("1.10"))
        stop_level = round(support * Decimal("0.97"), 2)
        target_1 = round(resistance * Decimal("1.02"), 2)
        target_2 = round(target_1 * Decimal("1.08"), 2)

        risk = max(Decimal("1.0"), current_price - stop_level)
        reward = max(Decimal("1.0"), target_1 - current_price)
        rr_ratio = round(float(reward / risk), 1)

        new_investor_rec = {
            "status": "WAIT FOR PULLBACK",
            "entry_zone": f"₹{round(support * Decimal('1.01'), 2)} - ₹{round(current_price * Decimal('0.99'), 2)}",
            "stop_loss": f"₹{stop_level}",
            "target_levels": [f"₹{target_1}", f"₹{target_2}"],
            "risk_reward": f"1 : {rr_ratio}",
            "suitable_horizon": "Swing / Medium-Term (4 to 12 weeks)",
            "conditions": [
                "Price stabilizes at or near key structural support.",
                "Daily RSI holds above 40 during consolidation.",
                "Volume expands on green rebound candles.",
            ],
        }

        if tech_trend == "BULLISH" and rr_ratio >= 2.0:
            new_investor_rec["status"] = "FAVORABLE ENTRY"
        elif tech_trend == "BEARISH":
            new_investor_rec["status"] = "AVOID / WAIT"
            new_investor_rec["conditions"].append("Wait for reversal pattern confirmation above 50 EMA.")

        return {
            "existing_holder": holder_rec,
            "new_investor": new_investor_rec,
        }
