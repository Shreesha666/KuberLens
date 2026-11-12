"""
Management command to import user's actual stock holdings into the platform database,
create missing canonical instruments, record ledger transactions, and reconcile FIFO positions.
"""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.holdings.models import Holding, HoldingTransaction, LotAllocation, TransactionType
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.portfolio.models import Portfolio
from services.portfolio.accounting import FIFOAccountingEngine

logger = logging.getLogger(__name__)
User = get_user_model()

HOLDINGS_DATA = [
    {
        "symbol": "BANKINDIA",
        "display_name": "Bank of India",
        "legal_name": "Bank of India Limited",
        "sector": "Financial Services",
        "industry": "Public Sector Bank",
        "market_cap": "MID",
        "isin": "INE084A01016",
        "qty": 100,
        "avg_cost": Decimal("135.70"),
        "ltp": Decimal("150.60"),
        "invested": Decimal("13570.00"),
    },
    {
        "symbol": "COALINDIA",
        "display_name": "Coal India",
        "legal_name": "Coal India Limited",
        "sector": "Energy & Mining",
        "industry": "Coal Production",
        "market_cap": "LARGE",
        "isin": "INE522F01014",
        "qty": 43,
        "avg_cost": Decimal("392.30"),
        "ltp": Decimal("406.30"),
        "invested": Decimal("16868.90"),
    },
    {
        "symbol": "EIHOTEL",
        "display_name": "EIH Ltd (Oberoi)",
        "legal_name": "EIH Limited",
        "sector": "Consumer Services",
        "industry": "Hotels & Resorts",
        "market_cap": "MID",
        "isin": "INE230A01023",
        "qty": 40,
        "avg_cost": Decimal("494.90"),
        "ltp": Decimal("312.95"),
        "invested": Decimal("19796.00"),
    },
    {
        "symbol": "FCL",
        "display_name": "Fineotex Chemical",
        "legal_name": "Fineotex Chemical Limited",
        "sector": "Chemicals",
        "industry": "Specialty Chemicals",
        "market_cap": "SMALL",
        "isin": "INE045J01026",
        "qty": 143,
        "avg_cost": Decimal("48.46"),
        "ltp": Decimal("51.65"),
        "invested": Decimal("6929.95"),
    },
    {
        "symbol": "GAIL",
        "display_name": "GAIL (India)",
        "legal_name": "GAIL (India) Limited",
        "sector": "Utilities & Energy",
        "industry": "Natural Gas Transmission",
        "market_cap": "LARGE",
        "isin": "INE129A01019",
        "qty": 82,
        "avg_cost": Decimal("178.56"),
        "ltp": Decimal("189.90"),
        "invested": Decimal("14642.04"),
    },
    {
        "symbol": "IOC",
        "display_name": "Indian Oil Corp",
        "legal_name": "Indian Oil Corporation Limited",
        "sector": "Energy",
        "industry": "Oil Refining & Marketing",
        "market_cap": "LARGE",
        "isin": "INE242A01010",
        "qty": 175,
        "avg_cost": Decimal("151.57"),
        "ltp": Decimal("148.38"),
        "invested": Decimal("26524.10"),
    },
    {
        "symbol": "MICEL",
        "display_name": "MIC Electronics",
        "legal_name": "MIC Electronics Limited",
        "sector": "Capital Goods",
        "industry": "Electronic Equipment",
        "market_cap": "MICRO",
        "isin": "INE287C01029",
        "qty": 135,
        "avg_cost": Decimal("73.86"),
        "ltp": Decimal("39.50"),
        "invested": Decimal("9971.10"),
    },
    {
        "symbol": "MID150CASE",
        "display_name": "Nippon Midcap 150 ETF",
        "legal_name": "Nippon India ETF Nifty Midcap 150",
        "sector": "Index ETF",
        "industry": "Exchange Traded Funds",
        "market_cap": "MID",
        "isin": "INF204KB14I2",
        "qty": 1731,
        "avg_cost": Decimal("11.57"),
        "ltp": Decimal("11.38"),
        "invested": Decimal("20023.32"),
    },
    {
        "symbol": "MMTC",
        "display_name": "MMTC Ltd",
        "legal_name": "MMTC Limited",
        "sector": "Services & Trading",
        "industry": "Trading - Minerals & Metals",
        "market_cap": "MID",
        "isin": "INE123F01029",
        "qty": 149,
        "avg_cost": Decimal("113.40"),
        "ltp": Decimal("54.21"),
        "invested": Decimal("16897.27"),
    },
    {
        "symbol": "MOREPENLAB",
        "display_name": "Morepen Laboratories",
        "legal_name": "Morepen Laboratories Limited",
        "sector": "Healthcare",
        "industry": "Pharmaceuticals",
        "market_cap": "SMALL",
        "isin": "INE083A01026",
        "qty": 100,
        "avg_cost": Decimal("49.39"),
        "ltp": Decimal("96.74"),
        "invested": Decimal("4939.00"),
    },
    {
        "symbol": "NRBBEARING",
        "display_name": "NRB Bearings",
        "legal_name": "NRB Bearings Limited",
        "sector": "Automobile & Ancillaries",
        "industry": "Auto Parts & Equipment",
        "market_cap": "SMALL",
        "isin": "INE349A01021",
        "qty": 29,
        "avg_cost": Decimal("369.81"),
        "ltp": Decimal("431.70"),
        "invested": Decimal("10724.60"),
    },
    {
        "symbol": "PATELENG",
        "display_name": "Patel Engineering",
        "legal_name": "Patel Engineering Limited",
        "sector": "Infrastructure",
        "industry": "Construction & Civil Engineering",
        "market_cap": "SMALL",
        "isin": "INE244B01030",
        "qty": 130,
        "avg_cost": Decimal("65.90"),
        "ltp": Decimal("25.73"),
        "invested": Decimal("8566.50"),
    },
    {
        "symbol": "POWERGRID",
        "display_name": "Power Grid Corp",
        "legal_name": "Power Grid Corporation of India Limited",
        "sector": "Utilities",
        "industry": "Power Transmission",
        "market_cap": "LARGE",
        "isin": "INE752E01010",
        "qty": 56,
        "avg_cost": Decimal("272.62"),
        "ltp": Decimal("263.15"),
        "invested": Decimal("15266.45"),
    },
    {
        "symbol": "REDINGTON",
        "display_name": "Redington Ltd",
        "legal_name": "Redington Limited",
        "sector": "Technology",
        "industry": "IT Distribution & Supply Chain",
        "market_cap": "MID",
        "isin": "INE891D01026",
        "qty": 24,
        "avg_cost": Decimal("405.75"),
        "ltp": Decimal("344.30"),
        "invested": Decimal("9738.00"),
    },
    {
        "symbol": "RENUKA",
        "display_name": "Shree Renuka Sugars",
        "legal_name": "Shree Renuka Sugars Limited",
        "sector": "Consumer Goods & Agro",
        "industry": "Sugar & Bio-Ethanol",
        "market_cap": "MID",
        "isin": "INE087H01022",
        "qty": 1225,
        "avg_cost": Decimal("51.46"),
        "ltp": Decimal("18.85"),
        "invested": Decimal("63033.75"),
    },
    {
        "symbol": "SWSOLAR",
        "display_name": "Sterling & Wilson Renewable",
        "legal_name": "Sterling and Wilson Renewable Energy Limited",
        "sector": "Renewable Energy",
        "industry": "Solar Power EPC",
        "market_cap": "MID",
        "isin": "INE00M401021",
        "qty": 50,
        "avg_cost": Decimal("695.94"),
        "ltp": Decimal("163.52"),
        "invested": Decimal("34796.85"),
    },
    {
        "symbol": "TATSILV",
        "display_name": "Tata Silver ETF",
        "legal_name": "Tata Silver Exchange Traded Fund",
        "sector": "Commodities ETF",
        "industry": "Precious Metals ETF",
        "market_cap": "SMALL",
        "isin": "INF277K017V6",
        "qty": 471,
        "avg_cost": Decimal("21.12"),
        "ltp": Decimal("18.00"),
        "invested": Decimal("9947.52"),
    },
    {
        "symbol": "TRIDENT",
        "display_name": "Trident Ltd",
        "legal_name": "Trident Limited",
        "sector": "Textiles & Paper",
        "industry": "Home Textiles & Yarn",
        "market_cap": "MID",
        "isin": "INE064C01022",
        "qty": 500,
        "avg_cost": Decimal("47.95"),
        "ltp": Decimal("23.42"),
        "invested": Decimal("23975.00"),
    },
]


class Command(BaseCommand):
    help = "Imports user's actual portfolio holdings and reconciles FIFO positions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing holdings/transactions in portfolio before import.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Importing user stock holdings...")

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stderr.write("No users found.")
            return

        portfolio, _ = Portfolio.objects.get_or_create(
            user=user,
            is_default=True,
            defaults={"name": "My Equity Portfolio", "cash_balance": Decimal("50000.00"), "currency": "INR"},
        )
        portfolio.name = "My Equity Portfolio"
        portfolio.save()

        exchange, _ = Exchange.objects.get_or_create(
            code="NSE",
            defaults={"name": "National Stock Exchange", "country": "India", "currency": "INR"},
        )

        if options["clear"]:
            self.stdout.write("Clearing previous transactions and lot allocations...")
            LotAllocation.objects.filter(sell_transaction__portfolio=portfolio).delete()
            HoldingTransaction.objects.filter(portfolio=portfolio).delete()
            Holding.objects.filter(portfolio=portfolio).delete()

        now = timezone.now()

        total_imported_invested = Decimal("0.00")
        total_imported_value = Decimal("0.00")

        for item in HOLDINGS_DATA:
            # 1. Ensure canonical Instrument exists
            instrument, _ = Instrument.objects.update_or_create(
                isin=item["isin"],
                defaults={
                    "legal_name": item["legal_name"],
                    "display_name": item["display_name"],
                    "sector": item["sector"],
                    "industry": item["industry"],
                    "market_cap_category": item["market_cap"],
                },
            )

            # 2. Ensure ExchangeListing exists
            listing, _ = ExchangeListing.objects.update_or_create(
                symbol=item["symbol"],
                exchange=exchange,
                defaults={
                    "instrument": instrument,
                    "is_tradeable": True,
                },
            )

            # 3. Store/Update live/delayed MarketQuote
            MarketQuote.objects.update_or_create(
                listing=listing,
                retrieved_at=now,
                defaults={
                    "source_provider": "YAHOO",
                    "source_type": "DELAYED",
                    "freshness_status": "FRESH",
                    "source_timestamp": now,
                    "price": item["ltp"],
                    "open": item["avg_cost"],
                    "high": max(item["ltp"], item["avg_cost"]),
                    "low": min(item["ltp"], item["avg_cost"]),
                    "close": item["ltp"],
                    "previous_close": item["avg_cost"],
                    "change": item["ltp"] - item["avg_cost"],
                    "change_percent": (
                        ((item["ltp"] - item["avg_cost"]) / item["avg_cost"] * Decimal("100.0"))
                        if item["avg_cost"] > 0
                        else Decimal("0.00")
                    ),
                    "volume": 100000,
                    "configured_delay_minutes": 15,
                },
            )

            # 4. Clean previous transactions for this listing if any
            HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing).delete()

            # 5. Record core BUY transaction in immutable ledger
            HoldingTransaction.objects.create(
                portfolio=portfolio,
                listing=listing,
                transaction_type=TransactionType.BUY,
                quantity=item["qty"],
                price=item["avg_cost"],
                brokerage=Decimal("0.00"),
                statutory_taxes=Decimal("0.00"),
                executed_at=now - timedelta(days=60),
                notes="Portfolio position import",
            )

            # 6. Reconcile position using FIFO Accounting Engine
            holding = FIFOAccountingEngine.reconcile_holding(
                portfolio=portfolio,
                listing=listing,
                current_price=item["ltp"],
            )

            total_imported_invested += holding.invested_amount
            total_imported_value += holding.current_value

            self.stdout.write(
                f"  [{listing.symbol:12}] {holding.total_quantity:>5} sh @ ₹{holding.average_buy_price:>7.2f} "
                f"| LTP ₹{holding.current_price:>7.2f} | P&L: ₹{holding.unrealised_pnl:>9.2f} ({holding.unrealised_pnl_percent:>6.2f}%)"
            )

        pnl_diff = total_imported_value - total_imported_invested
        pnl_pct = (pnl_diff / total_imported_invested * Decimal("100.0")) if total_imported_invested > 0 else Decimal("0.0")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSuccessfully imported {len(HOLDINGS_DATA)} holdings into portfolio '{portfolio.name}'.\n"
                f"Total Invested: ₹{total_imported_invested:,.2f}\n"
                f"Current Value:  ₹{total_imported_value:,.2f}\n"
                f"Total P&L:      ₹{pnl_diff:,.2f} ({pnl_pct:.2f}%)"
            )
        )
