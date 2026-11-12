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
from apps.market.models import HistoricalCandle, MarketQuote
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
    "BANKINDIA": {
        "pe_ratio": 7.8,
        "pb_ratio": 0.88,
        "ps_ratio": 1.1,
        "ev_to_ebitda": 8.5,
        "dividend_yield": 2.8,
        "sector_pe": 11.5,
        "roe": 14.2,
        "roce": 12.8,
        "operating_margin": 24.0,
        "net_profit_margin": 16.5,
        "eps": 19.3,
        "debt_to_equity": 1.10,
        "current_ratio": 1.12,
        "interest_coverage_ratio": 3.8,
        "free_cash_flow": 6500.0,
        "revenue_growth_yoy": 16.2,
        "profit_growth_yoy": 24.8,
        "promoter_holding": 73.4,
        "fii_holding": 4.8,
        "dii_holding": 11.2,
        "public_holding": 10.6,
    },
    "EIHOTEL": {
        "pe_ratio": 34.5,
        "pb_ratio": 4.2,
        "ps_ratio": 5.1,
        "ev_to_ebitda": 18.2,
        "dividend_yield": 0.8,
        "sector_pe": 32.0,
        "roe": 15.8,
        "roce": 17.5,
        "operating_margin": 28.4,
        "net_profit_margin": 21.2,
        "eps": 9.1,
        "debt_to_equity": 0.18,
        "current_ratio": 1.85,
        "interest_coverage_ratio": 12.5,
        "free_cash_flow": 1200.0,
        "revenue_growth_yoy": 22.5,
        "profit_growth_yoy": 31.0,
        "promoter_holding": 35.2,
        "fii_holding": 18.5,
        "dii_holding": 26.1,
        "public_holding": 20.2,
    },
    "REDINGTON": {
        "pe_ratio": 14.2,
        "pb_ratio": 2.4,
        "ps_ratio": 0.4,
        "ev_to_ebitda": 9.2,
        "dividend_yield": 3.2,
        "sector_pe": 22.0,
        "roe": 20.5,
        "roce": 22.1,
        "operating_margin": 6.8,
        "net_profit_margin": 4.2,
        "eps": 24.2,
        "debt_to_equity": 0.22,
        "current_ratio": 1.65,
        "interest_coverage_ratio": 8.4,
        "free_cash_flow": 1850.0,
        "revenue_growth_yoy": 15.4,
        "profit_growth_yoy": 18.2,
        "promoter_holding": 0.0,
        "fii_holding": 52.4,
        "dii_holding": 21.2,
        "public_holding": 26.4,
    },
    "COALINDIA": {
        "pe_ratio": 8.1,
        "pb_ratio": 2.8,
        "ps_ratio": 1.8,
        "ev_to_ebitda": 5.4,
        "dividend_yield": 6.8,
        "sector_pe": 12.0,
        "roe": 42.5,
        "roce": 48.2,
        "operating_margin": 32.5,
        "net_profit_margin": 25.1,
        "eps": 50.1,
        "debt_to_equity": 0.11,
        "current_ratio": 1.95,
        "interest_coverage_ratio": 35.0,
        "free_cash_flow": 16200.0,
        "revenue_growth_yoy": 9.5,
        "profit_growth_yoy": 14.2,
        "promoter_holding": 66.1,
        "fii_holding": 8.5,
        "dii_holding": 15.8,
        "public_holding": 9.6,
    },
    "POWERGRID": {
        "pe_ratio": 16.8,
        "pb_ratio": 3.1,
        "ps_ratio": 3.8,
        "ev_to_ebitda": 9.8,
        "dividend_yield": 3.6,
        "sector_pe": 18.0,
        "roe": 19.2,
        "roce": 16.4,
        "operating_margin": 84.5,
        "net_profit_margin": 32.8,
        "eps": 15.7,
        "debt_to_equity": 1.38,
        "current_ratio": 0.95,
        "interest_coverage_ratio": 3.9,
        "free_cash_flow": 9800.0,
        "revenue_growth_yoy": 8.2,
        "profit_growth_yoy": 10.5,
        "promoter_holding": 51.3,
        "fii_holding": 31.2,
        "dii_holding": 12.8,
        "public_holding": 4.7,
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
    help = "Seeds historical candles (250 days), technical indicators, and fundamental snapshots for research."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreation of candles and recalculation of all indicators.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        listings = ExchangeListing.objects.filter(is_tradeable=True, is_primary=True).select_related("instrument")
        self.stdout.write(f"Seeding research data for {listings.count()} primary listings (force={force})...")

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

        # Select representative market trends
        BULLISH_SYMBOLS = {
            "RELIANCE", "TCS", "BHARTIARTL", "BANKINDIA", "EIHOTEL", "REDINGTON",
            "COALINDIA", "POWERGRID", "MOREPENLAB", "NRBBEARING"
        }
        BEARISH_SYMBOLS = {"PATELENG", "RENUKA", "MICEL", "SWSOLAR"}

        # Generate 250 trading day dates (excluding weekends) backwards from today
        trading_dates = []
        d = 0
        while len(trading_dates) < 250:
            day_date = (now - timedelta(days=d)).date()
            if day_date.weekday() not in (5, 6):
                trading_dates.append(day_date)
            d += 1
        trading_dates.reverse()  # Oldest to newest (today)

        for listing in listings:
            symbol = listing.symbol

            # Determine target final price
            quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
            if quote and quote.price > Decimal("0.0"):
                target_p = float(quote.price)
            elif symbol in base_prices:
                target_p = base_prices[symbol]
            else:
                target_p = 500.0

            existing_count = HistoricalCandle.objects.filter(listing=listing, interval="1d").count()
            if force or existing_count < 200:
                random.seed(42 + hash(symbol) % 1000)

                # Determine starting price based on trend type
                if symbol in BULLISH_SYMBOLS:
                    start_p = target_p * 0.72  # Solid 38% annual uptrend
                elif symbol in BEARISH_SYMBOLS:
                    start_p = target_p * 1.35  # Sustained downtrend
                else:
                    start_p = target_p * 0.96  # Mild consolidation / neutral

                N = len(trading_dates)
                daily_drift = (target_p / start_p) ** (1.0 / N) - 1.0

                current_p = start_p
                simulated_closes = []
                for _ in range(N):
                    noise = random.uniform(-0.015, 0.015)
                    current_p = current_p * (1.0 + daily_drift + noise)
                    simulated_closes.append(current_p)

                # Normalize so final candle strictly matches target_p
                scale = target_p / simulated_closes[-1]
                scaled_closes = [round(p * scale, 2) for p in simulated_closes]
                scaled_closes[-1] = round(target_p, 2)

                # Wipe previous seeded candles for this listing if replacing
                HistoricalCandle.objects.filter(listing=listing, interval="1d").delete()

                candles_to_create = []
                last_open = scaled_closes[0]
                last_high = scaled_closes[0]
                last_low = scaled_closes[0]
                last_close = scaled_closes[0]
                last_prev_close = scaled_closes[0]
                last_vol = 1000000

                for i, day_date in enumerate(trading_dates):
                    ts = datetime.combine(day_date, datetime.min.time(), tzinfo=UTC)
                    close_p = scaled_closes[i]
                    prev_p = scaled_closes[i - 1] if i > 0 else close_p
                    open_p = round(prev_p * (1 + random.uniform(-0.003, 0.003)), 2)
                    high_p = round(max(open_p, close_p) * (1 + random.uniform(0.002, 0.012)), 2)
                    low_p = round(min(open_p, close_p) * (1 - random.uniform(0.002, 0.012)), 2)
                    vol = random.randint(400000, 3000000)

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

                    last_open = open_p
                    last_high = high_p
                    last_low = low_p
                    last_close = close_p
                    last_prev_close = prev_p
                    last_vol = vol

                HistoricalCandle.objects.bulk_create(candles_to_create)
                self.stdout.write(f"[{symbol}] Created {len(candles_to_create)} historical candles.")

                # Keep MarketQuote perfectly synchronized with the terminal candle
                existing_quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
                if existing_quote:
                    existing_quote.source_provider = "SEEDED"
                    existing_quote.source_type = "DELAYED"
                    existing_quote.freshness_status = "FRESH"
                    existing_quote.source_timestamp = now
                    existing_quote.retrieved_at = now
                    existing_quote.price = Decimal(str(last_close))
                    existing_quote.open = Decimal(str(last_open))
                    existing_quote.high = Decimal(str(last_high))
                    existing_quote.low = Decimal(str(last_low))
                    existing_quote.close = Decimal(str(last_close))
                    existing_quote.previous_close = Decimal(str(last_prev_close))
                    existing_quote.change = Decimal(str(round(last_close - last_prev_close, 2)))
                    existing_quote.change_percent = (
                        Decimal(str(round((last_close - last_prev_close) / last_prev_close * 100, 2)))
                        if last_prev_close
                        else Decimal("0.0")
                    )
                    existing_quote.volume = last_vol
                    existing_quote.configured_delay_minutes = 15
                    existing_quote.save()
                else:
                    MarketQuote.objects.create(
                        listing=listing,
                        source_provider="SEEDED",
                        source_type="DELAYED",
                        freshness_status="FRESH",
                        source_timestamp=now,
                        retrieved_at=now,
                        price=Decimal(str(last_close)),
                        open=Decimal(str(last_open)),
                        high=Decimal(str(last_high)),
                        low=Decimal(str(last_low)),
                        close=Decimal(str(last_close)),
                        previous_close=Decimal(str(last_prev_close)),
                        change=Decimal(str(round(last_close - last_prev_close, 2))),
                        change_percent=(
                            Decimal(str(round((last_close - last_prev_close) / last_prev_close * 100, 2)))
                            if last_prev_close
                            else Decimal("0.0")
                        ),
                        volume=last_vol,
                        configured_delay_minutes=15,
                    )

            # 2. Compute Technical Indicators with full 200-period coverage
            all_candles = list(HistoricalCandle.objects.filter(listing=listing, interval="1d").order_by("timestamp"))
            TechnicalIndicatorCalculator.compute_and_store_snapshots(listing, all_candles)
            self.stdout.write(f"[{symbol}] Computed technical indicator snapshots ({len(all_candles)} candles).")

            # 3. Seed Fundamental Analysis
            fund_data = SAMPLE_FUNDAMENTALS.get(symbol, DEFAULT_METRICS)
            FundamentalAnalyzer.evaluate_instrument(listing.instrument, fund_data)
            self.stdout.write(f"[{symbol}] Compiled fundamental evaluation snapshot.")

        self.stdout.write(self.style.SUCCESS("Stock research data successfully seeded!"))
