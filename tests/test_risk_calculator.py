from decimal import Decimal

import pytest

from services.risk.calculator import PositionSizingResult, RiskCalculator


class TestRiskCalculator:
    def test_standard_position_sizing(self):
        """
        Trading Capital: ₹5,00,000
        Risk %: 1.0% -> Risk Amount = ₹5,000
        Entry: ₹1,000
        Stop Loss: ₹950 -> Risk Per Share = ₹50
        Quantity should be 5,000 / 50 = 100 shares.
        Required Capital = 100 * 1,000 = ₹1,00,000 (20% of account).
        """
        result = RiskCalculator.calculate_position_size(
            trading_capital=500000,
            risk_percentage=1.0,
            entry_price=1000,
            stop_loss=950,
            max_capital_pct=0.25,
        )

        assert isinstance(result, PositionSizingResult)
        assert result.quantity == 100
        assert result.risk_amount == Decimal("5000.00")
        assert result.risk_per_share == Decimal("50.0000")
        assert result.capital_required == Decimal("100000.00")
        assert result.capital_allocation_pct == Decimal("20.00")
        assert not result.is_over_allocated
        assert len(result.warnings) == 0

    def test_concentration_cap_enforcement(self):
        """
        Tight stop-loss would theoretically allow huge position size:
        Capital: ₹1,00,000, Risk 1% = ₹1,000
        Entry: ₹100, Stop Loss: ₹99 -> Risk per share: ₹1
        Raw quantity: 1,000 shares -> ₹1,00,000 required (100% of account!).
        Should be capped by max_capital_pct=0.20 to 200 shares (₹20,000 max).
        """
        result = RiskCalculator.calculate_position_size(
            trading_capital=100000,
            risk_percentage=1.0,
            entry_price=100,
            stop_loss=99,
            max_capital_pct=0.20,
        )

        assert result.quantity == 200
        assert result.capital_required == Decimal("20000.00")
        assert result.is_over_allocated is True
        assert any("concentration limit" in w for w in result.warnings)

    def test_stop_loss_equal_or_higher_than_entry_raises_error(self):
        """Zero and negative stop loss distance validation."""
        # Stop loss equals entry
        with pytest.raises(ValueError, match="must be strictly lower than entry price"):
            RiskCalculator.calculate_position_size(
                trading_capital=500000,
                risk_percentage=1.0,
                entry_price=1000,
                stop_loss=1000,
            )

        # Stop loss above entry
        with pytest.raises(ValueError, match="must be strictly lower than entry price"):
            RiskCalculator.calculate_position_size(
                trading_capital=500000,
                risk_percentage=1.0,
                entry_price=1000,
                stop_loss=1050,
            )

    def test_invalid_negative_or_zero_inputs(self):
        with pytest.raises(ValueError, match="Trading capital must be strictly positive"):
            RiskCalculator.calculate_position_size(
                trading_capital=0,
                risk_percentage=1.0,
                entry_price=100,
                stop_loss=95,
            )

        with pytest.raises(ValueError, match="Risk percentage must be strictly positive"):
            RiskCalculator.calculate_position_size(
                trading_capital=100000,
                risk_percentage=-1.0,
                entry_price=100,
                stop_loss=95,
            )

        with pytest.raises(ValueError, match="Entry price must be strictly positive"):
            RiskCalculator.calculate_position_size(
                trading_capital=100000,
                risk_percentage=1.0,
                entry_price=-100,
                stop_loss=95,
            )

    def test_high_risk_warning(self):
        """Warns if risk percentage > 2.5%."""
        result = RiskCalculator.calculate_position_size(
            trading_capital=500000,
            risk_percentage=3.0,
            entry_price=500,
            stop_loss=450,
        )
        assert any("exceeds recommended maximum" in w for w in result.warnings)

    def test_risk_reward_calculation(self):
        """
        Entry: ₹100
        Stop Loss: ₹90 (Risk: ₹10)
        Target: ₹125 (Reward: ₹25)
        R:R = 25 / 10 = 2.50
        """
        rr = RiskCalculator.calculate_risk_reward(
            entry_price=100,
            stop_loss=90,
            target_price=125,
        )
        assert rr == Decimal("2.50")

    def test_risk_reward_invalid_inputs(self):
        # Target below entry
        with pytest.raises(ValueError, match="Target price .* must be above entry price"):
            RiskCalculator.calculate_risk_reward(
                entry_price=100,
                stop_loss=90,
                target_price=95,
            )

        # Stop loss above entry
        with pytest.raises(ValueError, match="Stop-loss .* must be below entry price"):
            RiskCalculator.calculate_risk_reward(
                entry_price=100,
                stop_loss=105,
                target_price=120,
            )
