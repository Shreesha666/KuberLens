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
