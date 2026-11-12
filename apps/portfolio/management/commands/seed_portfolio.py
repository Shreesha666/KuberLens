"""
Management command to seed a realistic sample portfolio with multi-lot buys,
partial sells, dividend distributions, and positions for demonstration.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.holdings.models import HoldingTransaction, TransactionType
from apps.instruments.models import ExchangeListing
from apps.portfolio.models import Portfolio
from services.portfolio.accounting import FIFOAccountingEngine

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Seeds a demo portfolio with transactions and calculates FIFO positions."

    def handle(self, *args, **options):
        self.stdout.write("Seeding sample portfolio data...")

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stderr.write("No users found. Please create a user or superuser first.")
            return

        portfolio, created = Portfolio.objects.get_or_create(
            user=user,
            is_default=True,
            defaults={"name": "Long-Term Wealth", "cash_balance": Decimal("150000.00"), "currency": "INR"},
        )
        if created:
            self.stdout.write(f"Created default portfolio: {portfolio.name} for {user.email}")
        else:
            self.stdout.write(f"Using portfolio: {portfolio.name} for {user.email}")

        # Retrieve listings
        reliance = ExchangeListing.objects.filter(symbol="RELIANCE").first()
        tcs = ExchangeListing.objects.filter(symbol="TCS").first()
        hdfc = ExchangeListing.objects.filter(symbol="HDFCBANK").first()

        now = timezone.now()

        # 1. RELIANCE: Multi-lot Buy + Partial Sell + Dividend
        if reliance:
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=reliance).delete()

            # Lot 1: 50 shares @ 2800 (90 days ago)
            tx1 = HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=reliance,
                transaction_type=TransactionType.BUY,
                quantity=50,
                price=Decimal("2800.00"),
                brokerage=Decimal("20.00"),
                statutory_taxes=Decimal("35.00"),
                executed_at=now - timedelta(days=90),
                notes="Initial core position",
            )
            self.stdout.write(f"Logged {tx1}")

            # Lot 2: 30 shares @ 2900 (60 days ago)
            tx2 = HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=reliance,
                transaction_type=TransactionType.BUY,
                quantity=30,
                price=Decimal("2900.00"),
                brokerage=Decimal("20.00"),
                statutory_taxes=Decimal("22.00"),
                executed_at=now - timedelta(days=60),
                notes="DIP accumulation",
            )
            self.stdout.write(f"Logged {tx2}")

            # Sell: 30 shares @ 3050 (30 days ago) - should match against Lot 1 (50 shares @ ~2801.10)
            tx3 = HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=reliance,
                transaction_type=TransactionType.SELL,
                quantity=30,
                price=Decimal("3050.00"),
                brokerage=Decimal("20.00"),
                statutory_taxes=Decimal("25.00"),
                executed_at=now - timedelta(days=30),
                notes="Partial profit taking at target",
            )
            self.stdout.write(f"Logged {tx3}")

            # Dividend: Cash dividend of ₹10 per share on 50 remaining shares = ₹500
            tx4 = HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=reliance,
                transaction_type=TransactionType.DIVIDEND,
                quantity=50,
                price=Decimal("10.00"),
                executed_at=now - timedelta(days=15),
                notes="Annual dividend payout",
            )
            self.stdout.write(f"Logged {tx4}")

            FIFOAccountingEngine.reconcile_holding(portfolio, reliance)
            self.stdout.write("Reconciled RELIANCE positions.")

        # 2. TCS: Buy 20 shares @ 3950
        if tcs:
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=tcs).delete()
            HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=tcs,
                transaction_type=TransactionType.BUY,
                quantity=20,
                price=Decimal("3950.00"),
                brokerage=Decimal("20.00"),
                statutory_taxes=Decimal("20.00"),
                executed_at=now - timedelta(days=45),
                notes="IT large cap allocation",
            )
            FIFOAccountingEngine.reconcile_holding(portfolio, tcs)
            self.stdout.write("Reconciled TCS positions.")

        # 3. HDFCBANK: Buy 40 shares @ 1650
        if hdfc:
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=hdfc).delete()
            HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=hdfc,
                transaction_type=TransactionType.BUY,
                quantity=40,
                price=Decimal("1650.00"),
                brokerage=Decimal("20.00"),
                statutory_taxes=Decimal("18.00"),
                executed_at=now - timedelta(days=20),
                notes="Banking sector core holding",
            )
            FIFOAccountingEngine.reconcile_holding(portfolio, hdfc)
            self.stdout.write("Reconciled HDFCBANK positions.")

        self.stdout.write(self.style.SUCCESS("Portfolio successfully seeded and reconciled."))
