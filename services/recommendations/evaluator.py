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
        # 2. New Investor Guidance (Institutional Multi-Factor Engine)
        # ------------------------------------------------------------------
        tech_trend = technical.trend_signal if technical else "NEUTRAL"
        support = (
            technical.support_level
            if technical and technical.support_level and technical.support_level > Decimal("0.0")
            else (current_price * Decimal("0.95"))
        )
        resistance = (
            technical.resistance_level
            if technical and technical.resistance_level and technical.resistance_level > current_price
            else (current_price * Decimal("1.10"))
        )

        # 1. Volatility-Adjusted Stop Loss (ATR Chandelier Exit Logic)
        atr_val = (
            technical.atr_14
            if technical and technical.atr_14 and technical.atr_14 > Decimal("0.0")
            else (current_price * Decimal("0.025"))
        )
        atr_buffer = round(atr_val * Decimal("1.5"), 2)

        # Moving average dynamic support floor
        effective_support = support
        if technical and technical.ema_20 and technical.ema_20 < current_price:
            effective_support = max(effective_support, technical.ema_20)

        stop_level = round(effective_support - atr_buffer, 2)
        if stop_level >= current_price:
            stop_level = round(current_price * Decimal("0.96"), 2)
        if stop_level <= Decimal("0.0"):
            stop_level = round(current_price * Decimal("0.90"), 2)

        stop_loss_rationale = f"Structural Support (₹{effective_support:,.2f}) − 1.5× ATR Buffer (₹{atr_buffer:,.2f})"

        # 2. Multi-Stage Structural & Measured Targets
        if technical and technical.bollinger_upper and technical.bollinger_upper > current_price:
            target_1 = round(max(resistance, technical.bollinger_upper), 2)
        else:
            target_1 = round(max(resistance, current_price * Decimal("1.06")), 2)

        swing_high = technical.swing_high if technical and technical.swing_high else resistance
        swing_low = technical.swing_low if technical and technical.swing_low else effective_support
        measured_swing = max(Decimal("10.0"), swing_high - swing_low)
        target_2 = round(target_1 + (measured_swing * Decimal("0.618")), 2)
        if target_2 <= target_1:
            target_2 = round(target_1 * Decimal("1.08"), 2)

        # Fundamental Quality Floor & Multiple Expansion Buffer
        fund_score = fundamental.overall_score if fundamental else 50
        debt_to_equity = fundamental.debt_to_equity if fundamental else None
        is_fund_strong = fund_score >= 65 and (debt_to_equity is None or debt_to_equity <= Decimal("1.0"))
        is_fund_deteriorating = fund_score < 45 or (debt_to_equity is not None and debt_to_equity > Decimal("2.0"))

        if is_fund_strong:
            target_2 = round(target_2 * Decimal("1.03"), 2)

        # 3. Asymmetric Risk-to-Reward Ratio
        risk = max(Decimal("1.0"), current_price - stop_level)
        reward = max(Decimal("1.0"), target_1 - current_price)
        rr_ratio = round(float(reward / risk), 1)

        # 4. Institutional 4-Point Confluence Scoring
        check_trend = (tech_trend == "BULLISH")
        trend_detail = "Bullish momentum aligned above key moving averages." if check_trend else f"Trend signal is {tech_trend.capitalize()}."

        check_atr = (risk >= atr_val)
        atr_detail = f"Stop loss accounts for 1.5× ATR volatility cushion (₹{atr_buffer:,.2f})."

        rsi_val = float(technical.rsi_14) if technical and technical.rsi_14 else 50.0
        check_rsi = (40.0 <= rsi_val <= 70.0)
        rsi_detail = f"Daily RSI at {rsi_val:.1f} in accumulation sweet-spot (40–70)." if check_rsi else f"RSI at {rsi_val:.1f} ({'Overbought' if rsi_val > 70 else 'Momentum breakdown'})."

        check_fund = (fund_score >= 50)
        fund_detail = f"Corporate fundamental score of {fund_score}/100 provides valuation backing." if check_fund else f"Fundamental score of {fund_score}/100 indicates heightened risk."

        confluence_checks = [
            {"name": "Trend Momentum", "passed": check_trend, "detail": trend_detail},
            {"name": "ATR Volatility Buffer", "passed": check_atr, "detail": atr_detail},
            {"name": "RSI Momentum Zone", "passed": check_rsi, "detail": rsi_detail},
            {"name": "Fundamental Safety Floor", "passed": check_fund, "detail": fund_detail},
        ]
        passed_count = sum(1 for c in confluence_checks if c["passed"])
        confluence_score = int(passed_count / 4 * 100)

        # 5. Recommendation Status Classification
        if tech_trend == "BEARISH" or is_fund_deteriorating:
            status = "AVOID / WAIT"
        elif tech_trend == "BULLISH" and rr_ratio >= 1.8 and confluence_score >= 75:
            status = "FAVORABLE ENTRY"
        else:
            status = "WAIT FOR PULLBACK"

        new_investor_rec = {
            "status": status,
            "entry_zone": f"₹{round(effective_support * Decimal('1.005'), 2)} - ₹{round(current_price * Decimal('0.995'), 2)}",
            "stop_loss": f"₹{stop_level}",
            "stop_loss_value": float(stop_level),
            "stop_loss_rationale": stop_loss_rationale,
            "target_levels": [f"₹{target_1}", f"₹{target_2}"],
            "target_1_value": float(target_1),
            "target_2_value": float(target_2),
            "risk_reward": f"1 : {rr_ratio}",
            "rr_ratio_value": rr_ratio,
            "confluence_score": confluence_score,
            "confluence_checks": confluence_checks,
            "suitable_horizon": "Swing / Medium-Term (4 to 12 weeks)",
            "conditions": [c["detail"] for c in confluence_checks if not c["passed"]] or [
                "Price stabilizes at or near key structural support.",
                "Daily RSI holds above 40 during consolidation.",
                "Volume expands on green rebound candles.",
            ],
        }

        return {
            "existing_holder": holder_rec,
            "new_investor": new_investor_rec,
        }
