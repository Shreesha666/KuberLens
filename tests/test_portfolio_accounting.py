"""
Tests for Portfolio FIFO Accounting Engine, Immutable Ledger, and Corporate Actions.
Verifies capitalization of buy fees, deduction of sell fees, deterministic FIFO lot matching,
realized/unrealized P&L accuracy, reversals, stock splits, and bonus issues.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.holdings.models import (
    HoldingTransaction,
    LotAllocation,
    TransactionType,
)
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.portfolio.models import Portfolio
from services.portfolio.accounting import FIFOAccountingEngine

User = get_user_model()


@pytest.fixture
def test_setup(db):
    user = User.objects.create_user(
        username="investor_fifo",
        email="investor@example.com",
        password="password123",
    )
    portfolio = Portfolio.objects.create(
        user=user,
        name="Growth Portfolio",
        currency="INR",
        cash_balance=Decimal("500000.00"),
    )
    exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange")
    instrument = Instrument.objects.create(
        isin="INE002A01018",
        display_name="Reliance Industries",
        legal_name="Reliance Industries Limited",
        sector="Energy",
        industry="Oil & Gas",
    )
    listing = ExchangeListing.objects.create(
        instrument=instrument,
        exchange=exchange,
        symbol="RELIANCE",
        is_tradeable=True,
    )
    return {
        "user": user,
        "portfolio": portfolio,
        "listing": listing,
    }


@pytest.mark.django_db
class TestFIFOAccountingEngine:
    def test_single_buy_lot_fee_capitalization(self, test_setup):
        """Buy charges (brokerage + taxes) must be capitalized into effective unit cost."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]

        # 100 shares @ 2000.00, brokerage 20.00, taxes 30.00 -> Total cost = 200050.00
        # Unit cost = 2000.50
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=100,
            price=Decimal("2000.00"),
            brokerage=Decimal("20.00"),
            statutory_taxes=Decimal("30.00"),
            executed_at=timezone.now(),
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("2100.00"))

        assert holding.total_quantity == 100
        assert holding.invested_amount == Decimal("200050.00")
        assert holding.average_buy_price == Decimal("2000.5000")
        assert holding.current_value == Decimal("210000.00")
        assert holding.unrealised_pnl == Decimal("9950.00")
        assert holding.realised_pnl == Decimal("0.00")

    def test_multi_lot_fifo_partial_sell_with_deductions(self, test_setup):
        """Partial sell matches earliest open buy lot; sell charges reduce net proceeds."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]
        now = timezone.now()

        # Lot 1: 50 shares @ 1000.00 + 50.00 fees -> unit cost = 1001.00
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=50,
            price=Decimal("1000.00"),
            brokerage=Decimal("25.00"),
            statutory_taxes=Decimal("25.00"),
            executed_at=now - timedelta(days=20),
        )

        # Lot 2: 50 shares @ 1200.00 + 50.00 fees -> unit cost = 1201.00
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=50,
            price=Decimal("1200.00"),
            brokerage=Decimal("25.00"),
            statutory_taxes=Decimal("25.00"),
            executed_at=now - timedelta(days=10),
        )

        # Sell: 60 shares @ 1500.00 (gross = 90,000.00), sell fees = 60.00 -> net proceeds = 89,940.00
        # Under FIFO:
        # 1. 50 shares from Lot 1:
        #    Allocated cost basis = 50 * 1001.00 = 50,050.00
        #    Allocated net proceeds = 50 * (89940 / 60) = 50 * 1499.00 = 74,950.00
        #    Realized P&L = 74,950.00 - 50,050.00 = +24,900.00
        # 2. 10 shares from Lot 2:
        #    Allocated cost basis = 10 * 1201.00 = 12,010.00
        #    Allocated net proceeds = 10 * 1499.00 = 14,990.00
        #    Realized P&L = 14,990.00 - 12,010.00 = +2,980.00
        # Total Realized P&L = 24,900.00 + 2,980.00 = +27,880.00
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.SELL,
            quantity=60,
            price=Decimal("1500.00"),
            brokerage=Decimal("30.00"),
            statutory_taxes=Decimal("30.00"),
            executed_at=now,
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("1600.00"))

        # Remaining position: 40 shares from Lot 2
        assert holding.total_quantity == 40
        assert holding.average_buy_price == Decimal("1201.0000")
        assert holding.invested_amount == Decimal("48040.00")
        assert holding.realised_pnl == Decimal("27880.00")
        assert holding.current_value == Decimal("64000.00")
        assert holding.unrealised_pnl == Decimal("15960.00")

        # Verify LotAllocation audit trail
        allocations = list(LotAllocation.objects.all().order_by("buy_transaction__executed_at"))
        assert len(allocations) == 2
        assert allocations[0].matched_quantity == 50
        assert allocations[0].realised_pnl == Decimal("24900.00")
        assert allocations[1].matched_quantity == 10
        assert allocations[1].realised_pnl == Decimal("2980.00")

        # Verify open lots
        open_lots = FIFOAccountingEngine.get_open_lots(portfolio, listing)
        assert len(open_lots) == 1
        assert open_lots[0].remaining_quantity == 40
        assert open_lots[0].effective_unit_cost == Decimal("1201.0000")

    def test_reversal_transaction(self, test_setup):
        """Reversal entries cancel target transaction without deleting historical records."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]
        now = timezone.now()

        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=100,
            price=Decimal("500.00"),
            executed_at=now - timedelta(days=5),
        )

        # Accidental erroneous buy
        tx2 = HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=500,
            price=Decimal("500.00"),
            executed_at=now - timedelta(days=2),
        )

        # Reversal transaction referencing tx2
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY_REVERSAL,
            quantity=500,
            price=Decimal("500.00"),
            reference_transaction_id=tx2.id,
            executed_at=now - timedelta(days=1),
            notes="Erroneous order correction reversal",
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("550.00"))

        assert holding.total_quantity == 100
        assert holding.invested_amount == Decimal("50000.00")
        # All 3 records remain in the database for auditability
        assert HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing).count() == 3

    def test_bonus_issue_corporate_action(self, test_setup):
        """Bonus issue increases open lot quantities at zero acquisition cost, lowering unit cost."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]
        now = timezone.now()

        # Buy 100 shares @ 1000.00 (Total cost = 100,000.00)
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=100,
            price=Decimal("1000.00"),
            executed_at=now - timedelta(days=30),
        )

        # 1:1 Bonus issue (100 bonus shares awarded at 0 cost)
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BONUS,
            quantity=100,
            price=Decimal("0.00"),
            executed_at=now - timedelta(days=10),
            notes="1:1 Bonus issue",
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("600.00"))

        assert holding.total_quantity == 200
        # Total invested capital stays 100,000.00
        assert holding.invested_amount == Decimal("100000.00")
        # Average buy price halves to 500.00
        assert holding.average_buy_price == Decimal("500.0000")
        assert holding.current_value == Decimal("120000.00")
        assert holding.unrealised_pnl == Decimal("20000.00")

    def test_stock_split_corporate_action(self, test_setup):
        """Stock split splits lot shares and reduces unit cost basis proportionally."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]
        now = timezone.now()

        # Buy 20 shares @ 2500.00 (Cost = 50,000.00)
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=20,
            price=Decimal("2500.00"),
            executed_at=now - timedelta(days=30),
        )

        # 5:1 Stock split
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.SPLIT,
            quantity=5,
            split_ratio="5:1",
            executed_at=now - timedelta(days=5),
            notes="5:1 Stock split",
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("600.00"))

        assert holding.total_quantity == 100
        assert holding.invested_amount == Decimal("50000.00")
        assert holding.average_buy_price == Decimal("500.0000")
        assert holding.current_value == Decimal("60000.00")
        assert holding.unrealised_pnl == Decimal("10000.00")

    def test_cash_dividend_income(self, test_setup):
        """Cash dividends accrue dividend earnings without reducing share count or cost basis."""
        portfolio = test_setup["portfolio"]
        listing = test_setup["listing"]
        now = timezone.now()

        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.BUY,
            quantity=50,
            price=Decimal("1000.00"),
            executed_at=now - timedelta(days=20),
        )

        # ₹15 per share dividend on 50 shares = ₹750.00
        HoldingTransaction.objects.create(
            portfolio=portfolio,
            listing=listing,
            transaction_type=TransactionType.DIVIDEND,
            quantity=50,
            price=Decimal("15.00"),
            executed_at=now - timedelta(days=5),
        )

        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("1050.00"))

        assert holding.total_quantity == 50
        assert holding.dividend_earned == Decimal("750.00")
        assert holding.invested_amount == Decimal("50000.00")
