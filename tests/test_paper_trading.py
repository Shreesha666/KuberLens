"""
Tests for PaperTrading Module - Phase 1: Foundation & Models.
Validates virtual account auto-provisioning, financial properties,
order and position lifecycle, MTM PnL math, and account reset mechanics.
"""
from decimal import Decimal
import pytest

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.paper_trading.models import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperAccount,
    PaperOrder,
    PaperPosition,
    PaperTrade,
    PositionSide,
    ProductType,
)


@pytest.fixture
def paper_setup(db, django_user_model):
    user = django_user_model.objects.create_user(
        username="trader_vikram",
        email="vikram@example.com",
        password="securepass123",
    )
    exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
    instrument = Instrument.objects.create(
        isin="INE002A01018",
        display_name="RELIANCE",
        legal_name="Reliance Industries Limited",
        sector="Energy",
    )
    listing = ExchangeListing.objects.create(
        instrument=instrument,
        exchange=exchange,
        symbol="RELIANCE",
        is_tradeable=True,
    )
    account = PaperAccount.objects.get(user=user)
    return {
        "user": user,
        "exchange": exchange,
        "instrument": instrument,
        "listing": listing,
        "account": account,
    }


@pytest.mark.django_db
class TestPaperTradingModels:
    def test_auto_provisioning_signal_creates_account(self, paper_setup):
        """Verify new users automatically receive a PaperAccount with ₹10 Lakhs."""
        account = paper_setup["account"]
        assert account is not None
        assert account.initial_capital == Decimal("1000000.00")
        assert account.cash_balance == Decimal("1000000.00")
        assert account.available_margin == Decimal("1000000.00")
        assert account.margin_utilized == Decimal("0.00")
        assert account.realized_pnl == Decimal("0.00")
        assert account.is_active is True

    def test_paper_order_creation_and_properties(self, paper_setup):
        """Verify order lifecycle creation and status checks."""
        account = paper_setup["account"]
        listing = paper_setup["listing"]

        order = PaperOrder.objects.create(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.LIMIT,
            quantity=50,
            limit_price=Decimal("2500.00"),
            target_price=Decimal("2750.00"),
            stop_loss_price=Decimal("2380.00"),
            status=OrderStatus.PENDING,
        )

        assert order.is_active is True
        assert order.status == OrderStatus.PENDING
        assert order.quantity == 50
        assert order.target_price == Decimal("2750.00")
        assert "BUY 50x RELIANCE" in str(order)

    def test_long_position_mtm_recalculation(self, paper_setup):
        """Verify Long position invested value, current market value, and unrealized P&L."""
        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # User bought 100 shares @ ₹2,500 = ₹2,50,000 cost basis
        position = PaperPosition.objects.create(
            account=account,
            listing=listing,
            product_type=ProductType.CNC,
            quantity=100,
            average_price=Decimal("2500.00"),
            current_price=Decimal("2500.00"),
            unrealized_pnl=Decimal("0.00"),
        )

        assert position.side == PositionSide.LONG
        assert position.invested_value == Decimal("250000.00")
        assert position.current_market_value == Decimal("250000.00")
        assert position.unrealized_pnl_percent == Decimal("0.00")

        # Price rallies to ₹2,650 (+₹150/share, +6.0%)
        position.recalculate_pnl(Decimal("2650.00"))
        assert position.unrealized_pnl == Decimal("15000.00")
        assert position.unrealized_pnl_percent == Decimal("6.00")
        assert position.current_market_value == Decimal("265000.00")

        # Account properties reflect floating gain
        account.cash_balance = Decimal("750000.00")  # ₹10L - ₹2.5L invested
        account.save()
        assert account.unrealized_pnl == Decimal("15000.00")
        assert account.total_portfolio_value == Decimal("1015000.00")
        assert account.total_pnl == Decimal("15000.00")
        assert account.total_return_pct == Decimal("1.50")

    def test_short_intraday_position_mtm_recalculation(self, paper_setup):
        """Verify Short MIS position profit math on price drops."""
        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # Shorted 200 shares @ ₹2,500
        position = PaperPosition.objects.create(
            account=account,
            listing=listing,
            product_type=ProductType.MIS,
            quantity=-200,
            average_price=Decimal("2500.00"),
            current_price=Decimal("2500.00"),
            unrealized_pnl=Decimal("0.00"),
        )

        assert position.side == PositionSide.SHORT
        assert position.invested_value == Decimal("500000.00")

        # Price drops to ₹2,400 (Short makes +₹100/share = +₹20,000 gain)
        position.recalculate_pnl(Decimal("2400.00"))
        assert position.unrealized_pnl == Decimal("20000.00")
        assert position.unrealized_pnl_percent == Decimal("4.00")

    def test_paper_tradebook_itemized_record(self, paper_setup):
        """Verify executed tradebook record with Indian statutory tax itemization."""
        account = paper_setup["account"]
        listing = paper_setup["listing"]

        order = PaperOrder.objects.create(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.MARKET,
            quantity=100,
            status=OrderStatus.FILLED,
            filled_quantity=100,
        )

        trade = PaperTrade.objects.create(
            account=account,
            order=order,
            listing=listing,
            trade_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            execution_price=Decimal("2500.00"),
            quantity=100,
            turnover=Decimal("250000.00"),
            brokerage=Decimal("20.00"),
            stt=Decimal("250.00"),            # 0.1% of ₹2,50,000
            exchange_charges=Decimal("7.43"),
            gst=Decimal("4.94"),              # 18% of (20 + 7.43)
            sebi_charges=Decimal("0.25"),
            stamp_duty=Decimal("37.50"),       # 0.015% of ₹2,50,000
            total_charges=Decimal("320.12"),
        )

        assert trade.turnover == Decimal("250000.00")
        assert trade.total_charges == Decimal("320.12")
        assert "Trade: BUY 100x RELIANCE" in str(trade)

    def test_account_clean_reset(self, paper_setup):
        """Verify account reset cleans up positions, cancels open orders, and restores cash."""
        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # Create active position and pending order
        PaperPosition.objects.create(
            account=account,
            listing=listing,
            product_type=ProductType.CNC,
            quantity=50,
            average_price=Decimal("2500.00"),
            current_price=Decimal("2400.00"),
            unrealized_pnl=Decimal("-5000.00"),
        )
        pending_order = PaperOrder.objects.create(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.LIMIT,
            quantity=25,
            limit_price=Decimal("2300.00"),
            status=OrderStatus.PENDING,
        )

        account.cash_balance = Decimal("850000.00")
        account.realized_pnl = Decimal("-25000.00")
        account.save()

        # Reset account with ₹5,00,000 custom capital
        account.reset_account(new_capital=Decimal("500000.00"))

        account.refresh_from_db()
        assert account.initial_capital == Decimal("500000.00")
        assert account.cash_balance == Decimal("500000.00")
        assert account.realized_pnl == Decimal("0.00")
        assert account.positions.count() == 0

        pending_order.refresh_from_db()
        assert pending_order.status == OrderStatus.CANCELLED
        assert "Account reset" in pending_order.rejection_reason
