from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.trading.scanner import SwingScanner


@pytest.mark.django_db
class TestSwingScanner:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE123A01010",
            display_name="SWINGTEST",
            legal_name="Swing Test Limited",
            sector="Technology",
            industry="Software",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="SWINGTEST",
            trading_symbol="SWINGTEST-EQ",
            is_primary=True,
            is_tradeable=True,
        )
        self.now = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)

    def test_sma_pullback_setup_detection(self):
        """Bullish trend with price near 20 SMA produces SMA_PULLBACK setup."""
        MarketQuote.objects.create(
            listing=self.listing,
            source_provider="TEST",
            source_type="DIRECT",
            freshness_status="FRESH",
            source_timestamp=self.now,
            retrieved_at=self.now,
            price=Decimal("1000.00"),
            open=Decimal("995.00"),
            high=Decimal("1005.00"),
            low=Decimal("990.00"),
            close=Decimal("1000.00"),
            previous_close=Decimal("990.00"),
            change=Decimal("10.00"),
            change_percent=Decimal("1.01"),
            volume=1500000,
        )
        TechnicalIndicatorSnapshot.objects.create(
            listing=self.listing,
            timestamp=self.now,
            interval="1d",
            sma_20=Decimal("990.00"),   # within 1% of price
            sma_50=Decimal("940.00"),   # uptrend
            sma_200=Decimal("850.00"),  # strong uptrend
            rsi_14=Decimal("48.50"),    # neutral pullback RSI
            trend_signal="BULLISH",
            support_level=Decimal("940.00"),
            resistance_level=Decimal("1100.00"),
            swing_low=Decimal("940.00"),
            swing_high=Decimal("1100.00"),
        )

        setups = SwingScanner.scan_universe()
        assert len(setups) >= 1
        pullback = next((s for s in setups if s["strategy"] == "SMA_PULLBACK"), None)
        assert pullback is not None
        assert pullback["symbol"] == "SWINGTEST"
        assert pullback["stop_loss"] < pullback["current_price"]
        assert pullback["target_1"] > pullback["current_price"]
        assert pullback["risk_reward"] >= Decimal("1.50")
        assert "uptrend" in pullback["explanation"].lower()
        assert "invalidated if" in pullback["invalidation"].lower()

    def test_oversold_bounce_setup_detection(self):
        """Oversold RSI near support generates RSI_OVERSOLD_BOUNCE setup."""
        MarketQuote.objects.create(
            listing=self.listing,
            source_provider="TEST",
            source_type="DIRECT",
            freshness_status="FRESH",
            source_timestamp=self.now,
            retrieved_at=self.now,
            price=Decimal("500.00"),
            open=Decimal("502.00"),
            high=Decimal("505.00"),
            low=Decimal("498.00"),
            close=Decimal("500.00"),
            previous_close=Decimal("508.00"),
            change=Decimal("-8.00"),
            change_percent=Decimal("-1.57"),
            volume=800000,
        )
        TechnicalIndicatorSnapshot.objects.create(
            listing=self.listing,
            timestamp=self.now,
            interval="1d",
            sma_20=Decimal("540.00"),
            sma_50=Decimal("570.00"),
            sma_200=Decimal("600.00"),
            rsi_14=Decimal("28.00"),    # deeply oversold
            trend_signal="BEARISH",
            support_level=Decimal("495.00"), # near support
            resistance_level=Decimal("560.00"),
            swing_low=Decimal("490.00"),
            swing_high=Decimal("560.00"),
        )

        setups = SwingScanner.scan_universe()
        oversold = next((s for s in setups if s["strategy"] == "RSI_OVERSOLD_BOUNCE"), None)
        assert oversold is not None
        assert oversold["symbol"] == "SWINGTEST"
        assert oversold["stop_loss"] < Decimal("500.00")
        assert oversold["target_1"] > Decimal("500.00")
        assert oversold["risk_reward"] >= Decimal("1.50")

    def test_filter_by_strategy_and_market_cap(self):
        # Set up a stock with Bullish snapshot
        MarketQuote.objects.create(
            listing=self.listing,
            source_provider="TEST",
            source_type="DIRECT",
            freshness_status="FRESH",
            source_timestamp=self.now,
            retrieved_at=self.now,
            price=Decimal("1000.00"),
            open=Decimal("995.00"),
            high=Decimal("1005.00"),
            low=Decimal("990.00"),
            close=Decimal("1000.00"),
            previous_close=Decimal("990.00"),
            change=Decimal("10.00"),
            change_percent=Decimal("1.01"),
            volume=1500000,
        )
        TechnicalIndicatorSnapshot.objects.create(
            listing=self.listing,
            timestamp=self.now,
            interval="1d",
            sma_20=Decimal("990.00"),
            sma_50=Decimal("940.00"),
            sma_200=Decimal("850.00"),
            rsi_14=Decimal("48.50"),
            trend_signal="BULLISH",
            support_level=Decimal("940.00"),
            resistance_level=Decimal("1100.00"),
            swing_low=Decimal("940.00"),
            swing_high=Decimal("1100.00"),
        )

        # LARGE cap should match
        res_large = SwingScanner.scan_universe(market_cap_filter="LARGE")
        assert len(res_large) >= 1

        # MID cap should NOT match our LARGE listing
        res_mid = SwingScanner.scan_universe(market_cap_filter="MID")
        assert not any(s["symbol"] == "SWINGTEST" for s in res_mid)

        # Strategy filter
        res_pullback = SwingScanner.scan_universe(strategy_filter="SMA_PULLBACK")
        assert all(s["strategy"] == "SMA_PULLBACK" for s in res_pullback)
