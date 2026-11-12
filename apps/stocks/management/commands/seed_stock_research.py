"""
Management command to seed realistic sample historical candles, technical indicators,
and fundamental analysis snapshots for benchmark instruments.
"""
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle
from services.fundamentals.analyzer import FundamentalAnalyzer
from services.indicators.calculator import TechnicalIndicatorCalculator

SAMPLE_FUNDAMENTALS = {
    "RELIANCE": {
        "pe_ratio": 24.5,
        "pb_ratio": 2.2,
        "ps_ratio": 1.4,
        "ev_to_ebitda": 11.8,
        "dividend_yield": 0.35,
        "sector_pe": 22.0,
        "roe": 14.8,
        "roce": 12.5,
        "operating_margin": 16.2,
        "net_profit_margin": 9.4,
        "eps": 118.5,
        "debt_to_equity": 0.42,
        "current_ratio": 1.25,
        "interest_coverage_ratio": 7.2,
        "free_cash_flow": 28450.0,
        "revenue_growth_yoy": 11.2,
        "profit_growth_yoy": 14.5,
        "promoter_holding": 50.3,
        "fii_holding": 22.1,
        "dii_holding": 16.4,
        "public_holding": 11.2,
    },
    "TCS": {
        "pe_ratio": 29.8,
        "pb_ratio": 13.5,
        "ps_ratio": 6.2,
        "ev_to_ebitda": 19.5,
        "dividend_yield": 1.35,
        "sector_pe": 28.5,
        "roe": 48.2,
        "roce": 58.5,
        "operating_margin": 26.2,
        "net_profit_margin": 20.4,
        "eps": 128.5,
        "debt_to_equity": 0.0,
        "current_ratio": 2.85,
        "interest_coverage_ratio": 95.0,
        "free_cash_flow": 42000.0,
        "revenue_growth_yoy": 8.5,
        "profit_growth_yoy": 9.2,
        "promoter_holding": 71.8,
        "fii_holding": 12.5,
        "dii_holding": 10.2,
        "public_holding": 5.5,
    },
    "HDFCBANK": {
        "pe_ratio": 19.2,
        "pb_ratio": 2.8,
        "ps_ratio": 3.4,
        "ev_to_ebitda": 14.0,
        "dividend_yield": 1.15,
        "sector_pe": 18.5,
        "roe": 17.2,
        "roce": 16.5,
        "operating_margin": 28.5,
        "net_profit_margin": 24.2,
        "eps": 88.5,
        "debt_to_equity": 1.25,
        "current_ratio": 1.15,
        "interest_coverage_ratio": 4.5,
        "free_cash_flow": 18500.0,
        "revenue_growth_yoy": 18.5,
        "profit_growth_yoy": 20.2,
        "promoter_holding": 0.0,
        "fii_holding": 48.5,
        "dii_holding": 32.5,
        "public_holding": 19.0,
    },
    "INFY": {
        "pe_ratio": 26.5,
        "pb_ratio": 8.2,
        "ps_ratio": 4.5,
        "ev_to_ebitda": 17.2,
        "dividend_yield": 2.25,
        "sector_pe": 28.5,
        "roe": 31.5,
        "roce": 39.5,
        "operating_margin": 21.5,
        "net_profit_margin": 16.8,
        "eps": 62.5,
        "debt_to_equity": 0.08,
        "current_ratio": 2.15,
        "interest_coverage_ratio": 85.0,
        "free_cash_flow": 22000.0,
        "revenue_growth_yoy": 6.8,
        "profit_growth_yoy": 7.4,
        "promoter_holding": 14.8,
        "fii_holding": 34.2,
        "dii_holding": 36.5,
        "public_holding": 14.5,
    },
}

DEFAULT_METRICS = {
    "pe_ratio": 22.5,
    "pb_ratio": 3.5,
    "ps_ratio": 2.5,
    "ev_to_ebitda": 14.0,
    "dividend_yield": 1.2,
    "sector_pe": 24.0,
    "roe": 18.5,
    "roce": 20.5,
    "operating_margin": 18.0,
    "net_profit_margin": 14.0,
    "eps": 45.0,
    "debt_to_equity": 0.35,
    "current_ratio": 1.85,
    "interest_coverage_ratio": 15.0,
    "free_cash_flow": 8500.0,
    "revenue_growth_yoy": 12.0,
    "profit_growth_yoy": 14.5,
    "promoter_holding": 52.0,
    "fii_holding": 22.0,
    "dii_holding": 16.0,
    "public_holding": 10.0,
}


class Command(BaseCommand):
    help = "Seeds historical candles, technical indicators, and fundamental snapshots for research."

    def handle(self, *args, **options):
        listings = ExchangeListing.objects.filter(is_tradeable=True, is_primary=True).select_related("instrument")
        self.stdout.write(f"Seeding research data for {listings.count()} primary listings...")

        now = timezone.now()
        base_prices = {
            "RELIANCE": 2950.0,
            "TCS": 4150.0,
            "HDFCBANK": 1720.0,
            "INFY": 1860.0,
            "ICICIBANK": 1280.0,
            "SBIN": 840.0,
            "BHARTIARTL": 1650.0,
            "ITC": 490.0,
            "KOTAKBANK": 1780.0,
            "LT": 3650.0,
        }

        for listing in listings:
            symbol = listing.symbol
            base_p = base_prices.get(symbol, 1000.0)

            # 1. Seed 60 days of historical candles if none exist
            existing_count = HistoricalCandle.objects.filter(listing=listing, interval="1d").count()
            if existing_count < 30:
                random.seed(42 + hash(symbol) % 1000)
                candles_to_create = []
                current_p = base_p

                for d in range(60, 0, -1):
                    day_date = (now - timedelta(days=d)).date()
                    # Skip weekends
                    if day_date.weekday() in (5, 6):
                        continue

                    ts = datetime.combine(day_date, datetime.min.time(), tzinfo=UTC)
                    pct = random.uniform(-0.02, 0.025)
                    open_p = current_p
                    close_p = round(open_p * (1 + pct), 2)
                    high_p = round(max(open_p, close_p) * (1 + random.uniform(0.002, 0.015)), 2)
                    low_p = round(min(open_p, close_p) * (1 - random.uniform(0.002, 0.015)), 2)
                    vol = random.randint(500000, 3500000)

                    candles_to_create.append(
                        HistoricalCandle(
                            listing=listing,
                            timestamp=ts,
                            interval="1d",
                            open=Decimal(str(open_p)),
                            high=Decimal(str(high_p)),
                            low=Decimal(str(low_p)),
                            close=Decimal(str(close_p)),
                            volume=vol,
                            adjusted_close=Decimal(str(close_p)),
                            source_provider="SEEDED",
                        )
                    )
                    current_p = close_p

                HistoricalCandle.objects.bulk_create(candles_to_create, ignore_conflicts=True)
                self.stdout.write(f"[{symbol}] Created {len(candles_to_create)} historical candles.")

            # 2. Compute Technical Indicators
            all_candles = list(HistoricalCandle.objects.filter(listing=listing, interval="1d").order_by("timestamp"))
            TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, all_candles)
            self.stdout.write(f"[{symbol}] Computed technical indicator snapshots.")

            # 3. Seed Fundamental Analysis
            fund_data = SAMPLE_FUNDAMENTALS.get(symbol, DEFAULT_METRICS)
            FundamentalAnalyzer.evaluate_instrument(listing.instrument, fund_data)
            self.stdout.write(f"[{symbol}] Compiled fundamental evaluation snapshot.")

        self.stdout.write(self.style.SUCCESS("Stock research data successfully seeded!"))
