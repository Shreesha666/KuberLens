"""
AI Behavioral Coach & Discipline Audit Engine for Paper Trading.
Inspired by Open-Papertrade and quantitative trading psychology:
Analyzes user trade histories to detect cognitive biases, overtrading,
stop-loss adherence, and position sizing discipline.
"""
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import List

from django.utils import timezone

from apps.paper_trading.models import PaperAccount, PaperTrade


@dataclass
class CoachingInsight:
    category: str  # "STRENGTH", "WARNING", "OPPORTUNITY"
    title: str
    description: str
    impact: str    # "POSITIVE", "NEGATIVE", "NEUTRAL"


@dataclass
class BehavioralAuditReport:
    discipline_score: int                   # 0 to 100
    rating_label: str                       # Elite, Developing, High Risk
    stop_loss_coverage_pct: float           # % of trades with protective stop loss
    sizing_discipline_pct: float            # % of trades respecting <= 15% equity sizing
    overtrading_flag: bool                  # Triggered if > 6 trades in a day
    revenge_trading_detected: bool          # Rapid re-entry after loss
    insights: List[CoachingInsight] = field(default_factory=list)


class PaperTradingBehavioralCoach:
    """
    Evaluates trading psychological discipline and provides actionable coaching feedback.
    """
    @classmethod
    def audit_account(cls, account: PaperAccount) -> BehavioralAuditReport:
        trades = list(account.trades.select_related("listing", "order").order_by("executed_at"))
        total_trades = len(trades)

        if total_trades == 0:
            return BehavioralAuditReport(
                discipline_score=100,
                rating_label="Clean Slate",
                stop_loss_coverage_pct=100.0,
                sizing_discipline_pct=100.0,
                overtrading_flag=False,
                revenge_trading_detected=False,
                insights=[
                    CoachingInsight(
                        category="STRENGTH",
                        title="Ready for Execution",
                        description="Place your first simulated trade adhering to predefined risk-reward rules.",
                        impact="POSITIVE",
                    )
                ],
            )

        score = 100
        insights: List[CoachingInsight] = []

        # 1. Stop-Loss Coverage Audit
        trades_with_sl = sum(1 for t in trades if t.order.stop_loss_price is not None)
        sl_coverage_pct = round((trades_with_sl / total_trades) * 100.0, 1)

        if sl_coverage_pct >= 80.0:
            insights.append(
                CoachingInsight(
                    category="STRENGTH",
                    title="Exemplary Risk Protection",
                    description=f"{sl_coverage_pct}% of your trades had predefined protective stop-losses attached.",
                    impact="POSITIVE",
                )
            )
        elif sl_coverage_pct >= 50.0:
            score -= 15
            insights.append(
                CoachingInsight(
                    category="OPPORTUNITY",
                    title="Inconsistent Stop-Loss Usage",
                    description=f"Only {sl_coverage_pct}% of trades included a stop-loss. Aim for 100% bracket protection.",
                    impact="NEUTRAL",
                )
            )
        else:
            score -= 30
            insights.append(
                CoachingInsight(
                    category="WARNING",
                    title="Dangerous Naked Exposure",
                    description=f"Over {100.0 - sl_coverage_pct:.0f}% of trades lacked a stop-loss, exposing capital to uncapped tail risk.",
                    impact="NEGATIVE",
                )
            )

        # 2. Position Sizing & Concentration Cap Audit (Max 20% of capital)
        equity = account.total_portfolio_value or Decimal("1000000.00")
        max_recommended_size = equity * Decimal("0.20")
        oversized_trades = [t for t in trades if t.turnover > max_recommended_size]
        sizing_discipline_pct = round(((total_trades - len(oversized_trades)) / total_trades) * 100.0, 1)

        if not oversized_trades:
            insights.append(
                CoachingInsight(
                    category="STRENGTH",
                    title="Disciplined Capital Sizing",
                    description="All positions adhered to strict institutional allocation limits (<= 20% of equity).",
                    impact="POSITIVE",
                )
            )
        else:
            score -= min(25, len(oversized_trades) * 10)
            sample_sym = oversized_trades[0].listing.symbol
            insights.append(
                CoachingInsight(
                    category="WARNING",
                    title="Concentration Sizing Violation",
                    description=f"{len(oversized_trades)} trade(s) (e.g. {sample_sym}) exceeded 20% portfolio concentration.",
                    impact="NEGATIVE",
                )
            )

        # 3. Overtrading Velocity Audit (> 6 trades today)
        today = timezone.now().date()
        trades_today = [t for t in trades if t.executed_at.date() == today]
        overtrading_flag = len(trades_today) > 6

        if overtrading_flag:
            score -= 20
            insights.append(
                CoachingInsight(
                    category="WARNING",
                    title="Overtrading Velocity Detected",
                    description=f"You executed {len(trades_today)} trades today. High trade counts frequently correlate with commission drag and decision fatigue.",
                    impact="NEGATIVE",
                )
            )

        # 4. Revenge Trading Detector (Re-entry within 15 mins after a losing exit on same symbol)
        revenge_detected = False
        for i in range(len(trades) - 1):
            t1 = trades[i]
            t2 = trades[i + 1]
            if (
                t1.net_realized_pnl is not None
                and t1.net_realized_pnl < Decimal("0.00")
                and t1.listing_id == t2.listing_id
                and (t2.executed_at - t1.executed_at) < timedelta(minutes=15)
            ):
                revenge_detected = True
                break

        if revenge_detected:
            score -= 25
            insights.append(
                CoachingInsight(
                    category="WARNING",
                    title="Revenge Trading Impulse Detected",
                    description="Detected an immediate re-entry shortly after a losing exit on the same instrument. Maintain emotional neutrality and enforce cooldowns.",
                    impact="NEGATIVE",
                )
            )
        else:
            insights.append(
                CoachingInsight(
                    category="STRENGTH",
                    title="Emotional Impulse Control",
                    description="No hasty revenge trading re-entries identified following losing positions.",
                    impact="POSITIVE",
                )
            )

        final_score = max(0, min(100, score))
        if final_score >= 80:
            rating_label = "Institutional Grade Discipline (Elite)"
        elif final_score >= 60:
            rating_label = "Developing Professional (Consistent)"
        else:
            rating_label = "High Emotional Risk (Rule Violations)"

        return BehavioralAuditReport(
            discipline_score=final_score,
            rating_label=rating_label,
            stop_loss_coverage_pct=sl_coverage_pct,
            sizing_discipline_pct=sizing_discipline_pct,
            overtrading_flag=overtrading_flag,
            revenge_trading_detected=revenge_detected,
            insights=insights,
        )
