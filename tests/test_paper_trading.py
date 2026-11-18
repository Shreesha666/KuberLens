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


@pytest.mark.django_db
class TestPaperTradingExecutionAndTaxes:
    def test_tax_calculator_cnc_delivery_buy(self):
        """Verify Indian statutory charges on a ₹1,00,000 CNC Buy."""
        from services.paper_trading.tax_calculator import IndianTaxCalculator

        tax = IndianTaxCalculator.calculate(
            quantity=100,
            price=Decimal("1000.00"),  # Turnover = ₹1,00,000
            side="BUY",
            product_type="CNC",
        )
        assert tax.turnover == Decimal("100000.00")
        assert tax.brokerage == Decimal("20.00")       # Capped at ₹20
        assert tax.stt == Decimal("100.00")            # 0.1% on delivery
        assert tax.exchange_charges == Decimal("2.97") # 0.00297%
        assert tax.stamp_duty == Decimal("15.00")      # 0.015% on buy
        assert tax.gst == Decimal("4.13")              # 18% of (20 + 2.97) = 4.1346 -> 4.13
        assert tax.sebi_charges == Decimal("0.10")     # 0.0001%
        assert tax.total_charges > Decimal("140.00")

    def test_tax_calculator_mis_intraday_sell(self):
        """Verify STT and stamp duty exemption on MIS intraday sell."""
        from services.paper_trading.tax_calculator import IndianTaxCalculator

        tax = IndianTaxCalculator.calculate(
            quantity=100,
            price=Decimal("1000.00"),  # Turnover = ₹1,00,000
            side="SELL",
            product_type="MIS",
        )
        assert tax.turnover == Decimal("100000.00")
        assert tax.stt == Decimal("25.00")             # 0.025% on MIS sell
        assert tax.stamp_duty == Decimal("0.00")       # Stamp duty is ₹0 on sell

    def test_market_buy_execution_and_slippage(self, paper_setup):
        """Verify market order placement immediately executes with realistic slippage."""
        from apps.market.models import MarketQuote
        from services.paper_trading.engine import PaperTradingExecutionEngine
        from django.utils import timezone

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # Mock current quote at ₹2,500
        MarketQuote.objects.create(
            listing=listing,
            price=Decimal("2500.00"),
            change=Decimal("10.00"),
            change_percent=Decimal("0.40"),
            open=Decimal("2490.00"),
            high=Decimal("2510.00"),
            low=Decimal("2485.00"),
            close=Decimal("2500.00"),
            previous_close=Decimal("2490.00"),
            volume=100000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        initial_cash = account.cash_balance
        order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.MARKET,
            quantity=10,
        )

        assert order.status == OrderStatus.FILLED
        assert order.filled_quantity == 10
        # Ask price includes +0.05% slippage: 2500 * 1.0005 = 2501.25
        trade = order.trades.first()
        assert trade is not None
        assert trade.execution_price == Decimal("2501.25")
        assert trade.turnover == Decimal("25012.50")

        # Position is created
        pos = PaperPosition.objects.get(account=account, listing=listing, product_type=ProductType.CNC)
        assert pos.quantity == 10
        assert pos.average_price == Decimal("2501.25")

        # Cash balance deducted by turnover + charges
        account.refresh_from_db()
        assert account.cash_balance < initial_cash - Decimal("25012.50")

    def test_insufficient_margin_rejection(self, paper_setup):
        """Verify orders exceeding available cash are cleanly rejected."""
        from services.paper_trading.engine import PaperTradingExecutionEngine

        account = paper_setup["account"]
        listing = paper_setup["listing"]
        account.cash_balance = Decimal("5000.00")
        account.save()

        order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=Decimal("2500.00"),  # Requires ₹2,50,000 > ₹5,000 available
        )

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient funds" in order.rejection_reason

    def test_cnc_sell_without_holdings_rejected(self, paper_setup):
        """Verify delivery sell is rejected when user has no underlying holdings."""
        from services.paper_trading.engine import PaperTradingExecutionEngine

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.SELL,
            product_type=ProductType.CNC,
            order_type=OrderType.MARKET,
            quantity=50,
        )

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient CNC holdings" in order.rejection_reason

    def test_limit_order_pending_and_cancellation(self, paper_setup):
        """Verify limit order locking margin and unlocking upon cancellation."""
        from apps.market.models import MarketQuote
        from services.paper_trading.engine import PaperTradingExecutionEngine
        from django.utils import timezone

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # Market is currently ₹2,500
        MarketQuote.objects.create(
            listing=listing,
            price=Decimal("2500.00"),
            change=Decimal("0.00"),
            change_percent=Decimal("0.00"),
            open=Decimal("2500.00"),
            high=Decimal("2500.00"),
            low=Decimal("2500.00"),
            close=Decimal("2500.00"),
            previous_close=Decimal("2500.00"),
            volume=50000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        # Place BUY limit below market: 100 shares @ ₹2,000 = ₹2,00,000 margin
        order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.LIMIT,
            quantity=100,
            limit_price=Decimal("2000.00"),
        )

        assert order.status == OrderStatus.PENDING
        account.refresh_from_db()
        assert account.margin_utilized == Decimal("200000.00")

        # Cancel order
        success = PaperTradingExecutionEngine.cancel_order(order)
        assert success is True
        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED

        # Margin is unlocked
        account.refresh_from_db()
        assert account.margin_utilized == Decimal("0.00")

    def test_roundtrip_buy_and_sell_realized_pnl(self, paper_setup):
        """Verify full round-trip trade: Buy 100 @ 1,000, Sell 100 @ 1,100."""
        from apps.market.models import MarketQuote
        from services.paper_trading.engine import PaperTradingExecutionEngine
        from django.utils import timezone

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        q = MarketQuote.objects.create(
            listing=listing,
            price=Decimal("1000.00"),
            change=Decimal("0.00"),
            change_percent=Decimal("0.00"),
            open=Decimal("1000.00"),
            high=Decimal("1000.00"),
            low=Decimal("1000.00"),
            close=Decimal("1000.00"),
            previous_close=Decimal("1000.00"),
            volume=50000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        # 1. Buy 100 shares
        buy_order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.BUY,
            product_type=ProductType.CNC,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        assert buy_order.status == OrderStatus.FILLED

        pos = PaperPosition.objects.get(account=account, listing=listing, product_type=ProductType.CNC)
        assert pos.quantity == 100

        # 2. Market rallies to ₹1,100
        q.price = Decimal("1100.00")
        q.save()

        # 3. Sell 100 shares
        sell_order = PaperTradingExecutionEngine.place_order(
            account=account,
            listing=listing,
            order_side=OrderSide.SELL,
            product_type=ProductType.CNC,
            order_type=OrderType.MARKET,
            quantity=100,
        )
        assert sell_order.status == OrderStatus.FILLED

        # Position should be closed and deleted
        assert PaperPosition.objects.filter(account=account, listing=listing).count() == 0

        # Account should register net positive realized P&L (~₹9,500 after taxes)
        account.refresh_from_db()
        assert account.realized_pnl > Decimal("9000.00")
        sell_trade = sell_order.trades.first()
        assert sell_trade.net_realized_pnl is not None
        assert sell_trade.net_realized_pnl > Decimal("9000.00")

    def test_square_off_position_helper(self, paper_setup):
        """Verify square_off_position closes out an active position."""
        from services.paper_trading.engine import PaperTradingExecutionEngine

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        # User has Long position of 50 shares
        pos = PaperPosition.objects.create(
            account=account,
            listing=listing,
            product_type=ProductType.CNC,
            quantity=50,
            average_price=Decimal("100.00"),
            current_price=Decimal("100.00"),
        )

        exit_order = PaperTradingExecutionEngine.square_off_position(pos)
        assert exit_order is not None
        assert exit_order.status == OrderStatus.FILLED
        assert exit_order.order_side == OrderSide.SELL
        assert exit_order.quantity == 50

        # Position should now be deleted
        assert PaperPosition.objects.filter(account=account, listing=listing).count() == 0

    def test_bracket_target_and_stop_loss_trigger(self, paper_setup):
        """Verify pending bracket orders auto-squareoff when market touches target."""
        from apps.market.models import MarketQuote
        from services.paper_trading.engine import PaperTradingExecutionEngine
        from django.utils import timezone

        account = paper_setup["account"]
        listing = paper_setup["listing"]

        quote = MarketQuote.objects.create(
            listing=listing,
            price=Decimal("1000.00"),
            change=Decimal("0.00"),
            change_percent=Decimal("0.00"),
            open=Decimal("1000.00"),
            high=Decimal("1000.00"),
            low=Decimal("1000.00"),
            close=Decimal("1000.00"),
            previous_close=Decimal("1000.00"),
            volume=50000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        # Position with Target = ₹1,100, Stop Loss = ₹950
        PaperPosition.objects.create(
            account=account,
            listing=listing,
            product_type=ProductType.CNC,
            quantity=10,
            average_price=Decimal("1000.00"),
            current_price=Decimal("1000.00"),
            target=Decimal("1100.00"),
            stop_loss=Decimal("950.00"),
        )

        # Market rallies to ₹1,120 (Target triggered)
        quote.price = Decimal("1120.00")
        quote.save()

        PaperTradingExecutionEngine.evaluate_pending_orders_and_brackets(account=account)

        # Position auto-squared off
        assert PaperPosition.objects.filter(account=account, listing=listing).count() == 0


@pytest.mark.django_db
class TestPaperTradingViews:
    def test_order_drawer_get_anonymous_redirect(self, client, paper_setup):
        """Anonymous user is redirected to login."""
        listing = paper_setup["listing"]
        from django.urls import reverse

        url = reverse("paper_trading:order_drawer", kwargs={"symbol": listing.symbol})
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_order_drawer_get_authenticated(self, client, paper_setup):
        """Authenticated user gets drawer partial with prefilled quote and margin."""
        user = paper_setup["user"]
        listing = paper_setup["listing"]
        from django.urls import reverse

        client.force_login(user)
        url = reverse("paper_trading:order_drawer", kwargs={"symbol": listing.symbol})
        response = client.get(url)

        assert response.status_code == 200
        assert listing.symbol.encode() in response.content
        assert b"Available Cash:" in response.content
        assert b"paperOrderOffcanvas" in response.content

    def test_estimate_charges_api(self, client, paper_setup):
        """Verify the estimate charges JSON API returns accurate calculations."""
        user = paper_setup["user"]
        from django.urls import reverse

        client.force_login(user)
        url = reverse("paper_trading:estimate_charges")
        response = client.get(url, {
            "quantity": 100,
            "price": "1000.00",
            "side": "BUY",
            "product_type": "CNC",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["turnover"] == 100000.00
        assert data["brokerage"] == 20.00
        assert data["stt"] == 100.00
        assert data["total_charges"] > 140.00

    def test_place_order_post_success(self, client, paper_setup):
        """Placing a valid market buy order executes and returns confirmation."""
        user = paper_setup["user"]
        listing = paper_setup["listing"]
        from apps.market.models import MarketQuote
        from django.utils import timezone
        from django.urls import reverse

        MarketQuote.objects.create(
            listing=listing,
            price=Decimal("1500.00"),
            change=Decimal("0.00"),
            change_percent=Decimal("0.00"),
            open=Decimal("1500.00"),
            high=Decimal("1500.00"),
            low=Decimal("1500.00"),
            close=Decimal("1500.00"),
            previous_close=Decimal("1500.00"),
            volume=20000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        client.force_login(user)
        url = reverse("paper_trading:order_place")
        response = client.post(url, {
            "symbol": listing.symbol,
            "order_side": "BUY",
            "product_type": "CNC",
            "order_type": "MARKET",
            "quantity": 10,
        })

        assert response.status_code == 200
        assert b"Order Executed Successfully" in response.content
        assert b"FILLED" in response.content

        # Verify database record
        order = PaperOrder.objects.filter(account__user=user, listing=listing).first()
        assert order is not None
        assert order.status == OrderStatus.FILLED

    def test_place_order_post_rejection_no_holdings(self, client, paper_setup):
        """Attempting to sell CNC without holdings returns Order Rejected partial."""
        user = paper_setup["user"]
        listing = paper_setup["listing"]
        from django.urls import reverse

        client.force_login(user)
        url = reverse("paper_trading:order_place")
        response = client.post(url, {
            "symbol": listing.symbol,
            "order_side": "SELL",
            "product_type": "CNC",
            "order_type": "MARKET",
            "quantity": 50,
        })

        assert response.status_code == 200
        assert b"Order Rejected" in response.content
        assert b"Insufficient CNC holdings" in response.content

