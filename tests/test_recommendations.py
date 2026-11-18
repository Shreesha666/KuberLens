"""
Tests for Dual-Perspective Recommendation Evaluator.
Verifies existing holder vs new prospective investor strategy derivation,
concentration risk warnings, and the strict prohibition against averaging down on deteriorating fundamentals.
"""
from decimal import Decimal

import pytest

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.portfolio.models import Portfolio
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.recommendations.evaluator import RecommendationEvaluator


@pytest.fixture
def eval_setup(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="analyst_test",
        email="analyst@example.com",
        password="pass",
    )
    portfolio = Portfolio.objects.create(user=user, name="Main")
    exchange = Exchange.objects.create(code="NSE", name="NSE")
    instrument = Instrument.objects.create(
        isin="INE001A01001",
        display_name="Test Stock Ltd",
        legal_name="Test Stock Limited",
        sector="Technology",
    )
    listing = ExchangeListing.objects.create(
        instrument=instrument,
        exchange=exchange,
        symbol="TEST",
        is_tradeable=True,
    )
    return {
        "user": user,
        "portfolio": portfolio,
        "instrument": instrument,
        "listing": listing,
    }


@pytest.mark.django_db
class TestRecommendationEvaluator:
    def test_non_holder_receives_new_investor_guidance(self, eval_setup):
        listing = eval_setup["listing"]

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=None,
            technical=None,
            fundamental=None,
        )

        assert result["existing_holder"]["is_holder"] is False
        assert result["existing_holder"]["action"] == "N/A"
        assert result["new_investor"]["status"] in ("WAIT FOR PULLBACK", "FAVORABLE ENTRY", "AVOID / WAIT")
        assert "stop_loss" in result["new_investor"]
        assert "target_levels" in result["new_investor"]

    def test_profit_booking_recommendation_on_large_gain(self, eval_setup):
        portfolio = eval_setup["portfolio"]
        listing = eval_setup["listing"]

        holding = Holding.objects.create(
            portfolio=portfolio,
            listing=listing,
            total_quantity=100,
            average_buy_price=Decimal("1000.00"),
            invested_amount=Decimal("100000.00"),
            current_price=Decimal("1350.00"),
            current_value=Decimal("135000.00"),
            unrealised_pnl=Decimal("35000.00"),
            unrealised_pnl_percent=Decimal("35.00"),
        )

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=holding,
            portfolio_total_value=Decimal("1000000.00"),
        )

        assert result["existing_holder"]["is_holder"] is True
        assert result["existing_holder"]["action"] == "PARTIAL PROFIT BOOKING"
        assert "Substantial unrealised gain" in result["existing_holder"]["reasoning"]

    def test_reduce_exposure_on_high_portfolio_concentration(self, eval_setup):
        portfolio = eval_setup["portfolio"]
        listing = eval_setup["listing"]

        # Stock represents 25% of total portfolio value
        holding = Holding.objects.create(
            portfolio=portfolio,
            listing=listing,
            total_quantity=100,
            average_buy_price=Decimal("1000.00"),
            invested_amount=Decimal("100000.00"),
            current_price=Decimal("1000.00"),
            current_value=Decimal("100000.00"),
            unrealised_pnl=Decimal("0.00"),
            unrealised_pnl_percent=Decimal("0.00"),
        )

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=holding,
            portfolio_total_value=Decimal("400000.00"),  # 100k / 400k = 25%
        )

        assert result["existing_holder"]["action"] == "REDUCE EXPOSURE"
        assert "Concentration risk" in result["existing_holder"]["reasoning"]

    def test_prohibit_averaging_down_on_deteriorating_fundamentals(self, eval_setup):
        """Must warn and prohibit averaging down when stock has >12% loss, bearish trend, and poor fundamental score."""
        portfolio = eval_setup["portfolio"]
        listing = eval_setup["listing"]
        instrument = eval_setup["instrument"]

        holding = Holding.objects.create(
            portfolio=portfolio,
            listing=listing,
            total_quantity=50,
            average_buy_price=Decimal("1000.00"),
            invested_amount=Decimal("50000.00"),
            current_price=Decimal("820.00"),
            current_value=Decimal("41000.00"),
            unrealised_pnl=Decimal("-9000.00"),
            unrealised_pnl_percent=Decimal("-18.00"),
        )

        from django.utils import timezone
        tech = TechnicalIndicatorSnapshot.objects.create(
            listing=listing,
            timestamp=timezone.now(),
            trend_signal="BEARISH",
        )
        fund = FundamentalSnapshot.objects.create(
            instrument=instrument,
            overall_score=35,  # Poor fundamental health
        )

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=holding,
            technical=tech,
            fundamental=fund,
            portfolio_total_value=Decimal("500000.00"),
        )

        assert result["existing_holder"]["action"] == "EXIT"
        assert result["existing_holder"]["warning"] is not None
        assert "DO NOT AVERAGE DOWN" in result["existing_holder"]["warning"]

    def test_favorable_entry_for_new_investor(self, eval_setup):
        listing = eval_setup["listing"]
        from django.utils import timezone
        tech = TechnicalIndicatorSnapshot.objects.create(
            listing=listing,
            timestamp=timezone.now(),
            trend_signal="BULLISH",
            bollinger_middle=Decimal("1000.00"),
            support_level=Decimal("980.00"),
            resistance_level=Decimal("1200.00"),
        )

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=None,
            technical=tech,
        )

        assert result["new_investor"]["status"] == "FAVORABLE ENTRY"
        assert "₹" in result["new_investor"]["entry_zone"]
        assert "1 :" in result["new_investor"]["risk_reward"]
        assert result["new_investor"]["confluence_score"] >= 75
        assert len(result["new_investor"]["confluence_checks"]) == 4
        assert "stop_loss_value" in result["new_investor"]
        assert "target_1_value" in result["new_investor"]
        assert "stop_loss_rationale" in result["new_investor"]

    def test_stale_pre_split_technical_guardrails(self, eval_setup):
        """
        Verify that if a stock underwent a split (e.g. current price ~1,000 but technical
        snapshot has pre-split resistance level ~7,000), the evaluator protects against
        absurd +500% targets and caps them to realistic swing projections.
        """
        listing = eval_setup["listing"]
        from django.utils import timezone
        from apps.market.models import MarketQuote

        now = timezone.now()
        quote = MarketQuote.objects.create(
            listing=listing,
            price=Decimal("1093.00"),
            change=Decimal("5.00"),
            change_percent=Decimal("0.46"),
            open=Decimal("1088.00"),
            high=Decimal("1098.00"),
            low=Decimal("1085.00"),
            close=Decimal("1093.00"),
            previous_close=Decimal("1088.00"),
            volume=500000,
            source_provider="YAHOO",
            source_timestamp=now,
            retrieved_at=now,
        )

        stale_tech = TechnicalIndicatorSnapshot.objects.create(
            listing=listing,
            timestamp=now,
            trend_signal="BULLISH",
            support_level=Decimal("6500.00"),   # Out of bounds (> current price)
            resistance_level=Decimal("7151.91"), # Stale pre-split resistance (+550%)
            swing_high=Decimal("7151.91"),
            swing_low=Decimal("6400.00"),
            atr_14=Decimal("180.00"),            # Stale pre-split ATR
            bollinger_upper=Decimal("7300.00"),
        )

        result = RecommendationEvaluator.evaluate(
            listing=listing,
            holding=None,
            technical=stale_tech,
            quote=quote,
        )

        new_rec = result["new_investor"]
        # Target 1 should NOT be 7,151.91 (+550%), but sane swing ~1,202 (+10%)
        assert new_rec["target_1_value"] < Decimal("1500.00")
        assert new_rec["target_1_pct"] <= Decimal("35.0")
        # Target 2 should also be within sane bounds
        assert new_rec["target_2_value"] < Decimal("1650.00")
        assert new_rec["target_2_pct"] <= Decimal("50.0")
        # Stop loss should be bounded relative to current price ~1,093, not ~6,000
        assert Decimal("900.00") <= new_rec["stop_loss_value"] < Decimal("1093.00")
