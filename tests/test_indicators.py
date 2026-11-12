"""
Unit tests for Technical Indicator Calculation Engine.
Verifies mathematical correctness of trend, momentum, volatility indicators, and signals.
Tests raw vs. derived separation and recalculation idempotency.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.indicators.calculator import TechnicalIndicatorCalculator


@pytest.fixture
def sample_listing(db):
    nse = Exchange.objects.create(code="NSE", name="National Stock Exchange")
    inst = Instrument.objects.create(
        isin="INE002A01018",
        legal_name="Reliance Industries Limited",
        display_name="Reliance",
        sector="Energy",
        industry="Refineries",
        market_cap_category="LARGE",
    )
    return ExchangeListing.objects.create(
        instrument=inst,
        exchange=nse,
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        is_tradeable=True,
    )


class TestTechnicalIndicatorMath:
    def test_sma_and_ema_calculation(self):
        # 30-day linear ascending series: 100, 101, ..., 129
        now = datetime(2024, 1, 1, tzinfo=UTC)
        records = [
            {
                "timestamp": now + timedelta(days=i),
                "open": 100.0 + i,
                "high": 102.0 + i,
                "low": 99.0 + i,
                "close": 100.0 + i,
                "volume": 100000,
            }
            for i in range(30)
        ]
        df = pd.DataFrame(records)
        df_calc = TechnicalIndicatorCalculator.calculate_dataframe(df)

        # SMA 20 on day 20 (index 19): avg of 100..119 = 109.5
        assert round(df_calc.loc[19, "sma_20"], 2) == 109.50
        # SMA 20 on day 30 (index 29): avg of 110..129 = 119.5
        assert round(df_calc.loc[29, "sma_20"], 2) == 119.50
        # EMA 9 exists and is numeric
        assert not pd.isna(df_calc.loc[29, "ema_9"])

    def test_macd_calculation(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        records = [
            {
                "timestamp": now + timedelta(days=i),
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.0 + (i * 2),  # Steady upward trend
                "volume": 100000,
            }
            for i in range(40)
        ]
        df = pd.DataFrame(records)
        df_calc = TechnicalIndicatorCalculator.calculate_dataframe(df)

        last_row = df_calc.iloc[-1]
        # Upward trend produces positive MACD line
        assert last_row["macd_line"] > 0
        # macd_histogram = macd_line - macd_signal
        assert round(last_row["macd_histogram"], 4) == round(last_row["macd_line"] - last_row["macd_signal"], 4)

    def test_rsi_extremes(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        # 1. Heavily rising prices -> RSI should be high (> 70)
        bullish_records = [
            {
                "timestamp": now + timedelta(days=i),
                "open": 100.0 + i * 5,
                "high": 105.0 + i * 5,
                "low": 98.0 + i * 5,
                "close": 102.0 + i * 5,
                "volume": 50000,
            }
            for i in range(25)
        ]
        df_bull = TechnicalIndicatorCalculator.calculate_dataframe(pd.DataFrame(bullish_records))
        assert df_bull.iloc[-1]["rsi_14"] >= 70.0
        assert df_bull.iloc[-1]["rsi_signal"] == "OVERBOUGHT"

        # 2. Heavily falling prices -> RSI should be low (< 30)
        bearish_records = [
            {
                "timestamp": now + timedelta(days=i),
                "open": 500.0 - i * 8,
                "high": 505.0 - i * 8,
                "low": 490.0 - i * 8,
                "close": 492.0 - i * 8,
                "volume": 50000,
            }
            for i in range(25)
        ]
        df_bear = TechnicalIndicatorCalculator.calculate_dataframe(pd.DataFrame(bearish_records))
        assert df_bear.iloc[-1]["rsi_14"] <= 30.0
        assert df_bear.iloc[-1]["rsi_signal"] == "OVERSOLD"

    def test_bollinger_bands_bounds(self):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        records = [
            {
                "timestamp": now + timedelta(days=i),
                "open": 200.0 + (i % 5),
                "high": 205.0 + (i % 5),
                "low": 195.0 + (i % 5),
                "close": 200.0 + (i % 5),
                "volume": 10000,
            }
            for i in range(30)
        ]
        df = pd.DataFrame(records)
        df_calc = TechnicalIndicatorCalculator.calculate_dataframe(df)

        for _, row in df_calc.iloc[20:].iterrows():
            assert row["bollinger_upper"] >= row["bollinger_middle"]
            assert row["bollinger_middle"] >= row["bollinger_lower"]

    def test_supertrend_calculation(self):
        highs = [105, 107, 108, 106, 109, 112, 110, 104, 102, 100, 98, 97]
        lows = [100, 102, 104, 103, 105, 108, 107, 100, 98, 95, 93, 92]
        closes = [104, 106, 107, 104, 108, 111, 108, 101, 99, 96, 94, 93]

        vals, dirs = TechnicalIndicatorCalculator.calculate_supertrend(highs, lows, closes, period=5, multiplier=2.0)
        assert len(vals) == len(closes)
        assert len(dirs) == len(closes)
        # Early bars with strong closes produce bullish direction (1)
        assert dirs[0] == 1
        # Late bars with sharp drops produce bearish direction (-1)
        assert dirs[-1] == -1
        assert all(v > 0 for v in vals)

    def test_parabolic_sar_calculation(self):
        highs = [100, 102, 105, 108, 112, 115, 110, 105, 100, 95]
        lows = [95, 97, 100, 104, 107, 110, 104, 100, 94, 90]
        closes = [99, 101, 104, 107, 111, 114, 105, 101, 95, 91]

        sar_vals, is_longs = TechnicalIndicatorCalculator.calculate_parabolic_sar(highs, lows, closes)
        assert len(sar_vals) == len(closes)
        assert len(is_longs) == len(closes)
        # In uptrend, SAR is below prices and is_long is True
        assert is_longs[1] is True
        assert sar_vals[1] <= lows[1]
        # In subsequent downtrend, SAR reverses and is_long becomes False
        assert is_longs[-1] is False
        assert sar_vals[-1] >= highs[-1]

    def test_fibonacci_retracements(self):
        highs = [100.0, 150.0, 200.0]
        lows = [80.0, 120.0, 100.0]

        fib = TechnicalIndicatorCalculator.calculate_fibonacci_levels(highs, lows)
        assert fib["swing_high"] == 200.0
        assert fib["swing_low"] == 80.0
        assert fib["diff"] == 120.0
        assert fib["level_0"] == 200.0
        assert fib["level_500"] == 140.0  # 200 - 0.5 * 120
        assert fib["level_618"] == round(200.0 - 0.618 * 120.0, 2)
        assert fib["level_100"] == 80.0


@pytest.mark.django_db
class TestTechnicalSnapshotRecalculation:
    def test_compute_and_store_snapshots(self, sample_listing):
        now = datetime(2024, 1, 1, tzinfo=UTC)
        candles = [
            HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=now + timedelta(days=i),
                interval="1d",
                open=Decimal(str(2500 + i * 10)),
                high=Decimal(str(2520 + i * 10)),
                low=Decimal(str(2490 + i * 10)),
                close=Decimal(str(2510 + i * 10)),
                volume=1000000,
                adjusted_close=Decimal(str(2510 + i * 10)),
                source_provider="TEST",
            )
            for i in range(35)
        ]

        # First calculation run
        snapshots = TechnicalIndicatorCalculator.compute_and_store_snapshots(sample_listing, candles)
        assert len(snapshots) == 35
        assert TechnicalIndicatorSnapshot.objects.filter(listing=sample_listing).count() == 35

        latest = TechnicalIndicatorSnapshot.objects.filter(listing=sample_listing).order_by("-timestamp").first()
        assert latest.calculation_version == "tech-v1.0.0"
        assert latest.sma_20 is not None

        # Recalculation idempotency test: second run updates without duplicate creation
        snapshots_v2 = TechnicalIndicatorCalculator.compute_and_store_snapshots(
            sample_listing, candles, calculation_version="tech-v1.0.0"
        )
        assert len(snapshots_v2) == 35
        assert TechnicalIndicatorSnapshot.objects.filter(listing=sample_listing).count() == 35
