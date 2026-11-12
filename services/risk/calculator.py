"""
Mathematical Risk Management & Position Sizing Engine.
Calculates position sizing based on trading capital, maximum risk percentage,
stop-loss distances, and enforces portfolio concentration constraints.
"""
import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass
class PositionSizingResult:
    trading_capital: Decimal
    risk_percentage: Decimal
    risk_amount: Decimal
    entry_price: Decimal
    stop_loss: Decimal
    risk_per_share: Decimal
    quantity: int
    capital_required: Decimal
    capital_allocation_pct: Decimal
    is_over_allocated: bool = False
    warnings: list[str] = field(default_factory=list)


class RiskCalculator:
    """
    Core quantitative risk management calculator.
    Enforces the golden rules of capital preservation:
    1. Risk per trade strictly capped at specified percentage of capital (default 1% - 2%).
    2. Position size strictly derived from stop-loss distance: Quantity = Risk Amount / Risk Per Share.
    3. Portfolio concentration limits preventing overallocation to a single position.
    4. Validation protecting against zero or negative stop-loss distances.
    """

    DEFAULT_RISK_PCT = Decimal("1.50")       # 1.5% account risk per swing trade
    DEFAULT_MAX_ALLOCATION_PCT = Decimal("0.20")  # Max 20% capital in any single position
    MIN_RISK_REWARD_RATIO = Decimal("1.50")  # Minimum 1:1.5 R:R required for swing setups

    @classmethod
    def calculate_position_size(
        cls,
        trading_capital: Decimal | float | str,
        risk_percentage: Decimal | float | str,
        entry_price: Decimal | float | str,
        stop_loss: Decimal | float | str,
        max_capital_pct: Decimal | float | str | None = None,
    ) -> PositionSizingResult:
        """
        Calculates position size using strict risk-per-share formulas.

        Formula:
            risk_amount = trading_capital * (risk_percentage / 100)
            risk_per_share = entry_price - stop_loss
            quantity = int(risk_amount / risk_per_share)
        """
        try:
            cap = Decimal(str(trading_capital))
            risk_pct = Decimal(str(risk_percentage))
            entry = Decimal(str(entry_price))
            sl = Decimal(str(stop_loss))
            max_alloc = Decimal(str(max_capital_pct or cls.DEFAULT_MAX_ALLOCATION_PCT))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ValueError(f"Invalid numeric input provided to position sizer: {e}") from e

        if cap <= Decimal("0.0"):
            raise ValueError("Trading capital must be strictly positive.")
        if risk_pct <= Decimal("0.0"):
            raise ValueError("Risk percentage must be strictly positive.")
        if entry <= Decimal("0.0"):
            raise ValueError("Entry price must be strictly positive.")
        if sl <= Decimal("0.0"):
            raise ValueError("Stop-loss price must be strictly positive.")
        if sl >= entry:
            raise ValueError(
                f"Invalid stop-loss: Stop-loss (₹{sl:.2f}) must be strictly lower "
                f"than entry price (₹{entry:.2f}) for long swing trades."
            )

        warnings: list[str] = []

        # 1. Calculate risk allowance in currency
        risk_amount = round(cap * (risk_pct / Decimal("100.0")), 2)

        # 2. Calculate risk per share
        risk_per_share = round(entry - sl, 4)
        if risk_per_share <= Decimal("0.0"):
            raise ValueError("Risk per share must be positive.")

        # 3. Base Quantity based on strictly allowed risk
        raw_quantity = int(risk_amount // risk_per_share)
        quantity = max(0, raw_quantity)

        # 4. Check Maximum Capital Allocation Constraint
        max_allowed_capital = round(cap * max_alloc, 2)
        capital_required = round(Decimal(quantity) * entry, 2)
        is_over_allocated = False

        if capital_required > max_allowed_capital:
            is_over_allocated = True
            # Cap quantity to the max allocation limit
            capped_qty = int(max_allowed_capital // entry)
            warnings.append(
                f"Position size was capped from {quantity} to {capped_qty} shares because required capital "
                f"(₹{capital_required:,.2f}) exceeded the maximum portfolio concentration limit of "
                f"{float(max_alloc * 100):.1f}% (₹{max_allowed_capital:,.2f})."
            )
            quantity = capped_qty
            capital_required = round(Decimal(quantity) * entry, 2)

        # 5. Warn if risk percentage is aggressively high (> 2.5%)
        if risk_pct > Decimal("2.50"):
            warnings.append(
                f"Caution: Risk of {risk_pct:.1f}% exceeds recommended maximum swing trading threshold of 2.0%."
            )

        # 6. Allocation percentage of total account
        capital_allocation_pct = round((capital_required / cap) * Decimal("100.0"), 2)

        return PositionSizingResult(
            trading_capital=cap,
            risk_percentage=risk_pct,
            risk_amount=risk_amount,
            entry_price=entry,
            stop_loss=sl,
            risk_per_share=risk_per_share,
            quantity=quantity,
            capital_required=capital_required,
            capital_allocation_pct=capital_allocation_pct,
            is_over_allocated=is_over_allocated,
            warnings=warnings,
        )

    @classmethod
    def calculate_risk_reward(
        cls,
        entry_price: Decimal | float | str,
        stop_loss: Decimal | float | str,
        target_price: Decimal | float | str,
    ) -> Decimal:
        """
        Calculates Risk-to-Reward ratio: (Target - Entry) / (Entry - StopLoss).
        """
        try:
            entry = Decimal(str(entry_price))
            sl = Decimal(str(stop_loss))
            target = Decimal(str(target_price))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ValueError(f"Invalid numeric input to risk-reward calculator: {e}") from e

        if sl >= entry:
            raise ValueError(f"Stop-loss ₹{sl:.2f} must be below entry price ₹{entry:.2f}.")
        if target <= entry:
            raise ValueError(f"Target price ₹{target:.2f} must be above entry price ₹{entry:.2f}.")

        risk = entry - sl
        reward = target - entry

        if risk <= Decimal("0.0"):
            raise ValueError("Risk must be greater than zero.")

        return round(reward / risk, 2)
