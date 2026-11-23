"""
Comprehensive test suite for Phase 2 Market Data infrastructure:
- MarketDataNormalizer sanity checks
- Data provider adapters (Jugaad & Yahoo)
- MarketDataService (caching, fallback, stale detection, historical candle retrieval)
- Data Sources UI View & HTMX partial rendering
- Celery scheduled tasks
"""
import zoneinfo
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import (
    DataQualityIssue,
    HistoricalCandle,
    MarketQuote,
)
from apps.market.tasks import ingest_daily_bhavcopy_task, monitor_provider_health_task
from integrations.market_data.base import (
    FreshnessStatus,
    HistoricalCandleDTO,
    MarketQuoteDTO,
    SourceType,
)
from integrations.market_data.exceptions import DataQualityError, ProviderConnectionError
from integrations.market_data.normalizer import MarketDataNormalizer
from integrations.market_data.providers.jugaad.adapter import JugaadDataProvider
from integrations.market_data.providers.yahoo.adapter import YahooFinanceProvider
from services.market_data.service import MarketDataService

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


@pytest.fixture
def sample_instruments(db):
    nse = Exchange.objects.create(code="NSE", name="National Stock Exchange")
    bse = Exchange.objects.create(code="BSE", name="Bombay Stock Exchange")

    inst = Instrument.objects.create(
        isin="INE002A01018",
        legal_name="Reliance Industries Limited",
        display_name="Reliance",
        sector="Energy",
        industry="Refineries",
        market_cap_category="LARGE",
    )

    nse_listing = ExchangeListing.objects.create(
        instrument=inst,
        exchange=nse,
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        series_or_group="EQ",
        is_tradeable=True,
    )

    bse_listing = ExchangeListing.objects.create(
        instrument=inst,
        exchange=bse,
        symbol="500325",
        trading_symbol="RELIANCE",
        series_or_group="A",
        is_tradeable=True,
    )

    return {"inst": inst, "nse": nse_listing, "bse": bse_listing}


# ----------------------------------------------------------------------
# 1. Normalizer Tests
# ----------------------------------------------------------------------
class TestMarketDataNormalizer:
    def test_candle_normalization_valid(self):
        dto = HistoricalCandleDTO(
            timestamp=datetime(2024, 2, 7, 10, 0, tzinfo=UTC),
            interval="1d",
            open=Decimal("2500.0"),
            high=Decimal("2550.0"),
            low=Decimal("2480.0"),
            close=Decimal("2520.0"),
            volume=1000000,
            adjusted_close=Decimal("2520.0"),
            source_provider="TEST",
        )
        validated = MarketDataNormalizer.validate_candle(dto)
        assert validated.open == Decimal("2500.0")
        assert validated.high == Decimal("2550.0")
        assert validated.low == Decimal("2480.0")
        assert validated.close == Decimal("2520.0")
        assert validated.volume == 1000000

    def test_candle_normalization_invalid_low_high(self):
        dto = HistoricalCandleDTO(
            timestamp=datetime(2024, 2, 7, 10, 0, tzinfo=UTC),
            interval="1d",
            open=Decimal("2500.0"),
            high=Decimal("2400.0"),  # Invalid: High < Low
            low=Decimal("2500.0"),
            close=Decimal("2450.0"),
            volume=100,
            adjusted_close=None,
            source_provider="TEST",
        )
        with pytest.raises(DataQualityError, match="Low price.*exceeds High price"):
            MarketDataNormalizer.validate_candle(dto)

    def test_candle_normalization_invalid_open_above_high(self):
        dto = HistoricalCandleDTO(
            timestamp=datetime(2024, 2, 7, 10, 0, tzinfo=UTC),
            interval="1d",
            open=Decimal("2600.0"),  # Open > High
            high=Decimal("2550.0"),
            low=Decimal("2400.0"),
            close=Decimal("2500.0"),
            volume=100,
            adjusted_close=None,
            source_provider="TEST",
        )
        with pytest.raises(DataQualityError, match="Open price.*outside bounds"):
            MarketDataNormalizer.validate_candle(dto)

    def test_candle_normalization_invalid_close_below_low(self):
        dto = HistoricalCandleDTO(
            timestamp=datetime(2024, 2, 7, 10, 0, tzinfo=UTC),
            interval="1d",
            open=Decimal("2500.0"),
            high=Decimal("2550.0"),
            low=Decimal("2450.0"),
            close=Decimal("2400.0"),  # Close < Low
            volume=100,
            adjusted_close=None,
            source_provider="TEST",
        )
        with pytest.raises(DataQualityError, match="Close price.*outside bounds"):
            MarketDataNormalizer.validate_candle(dto)

    def test_candle_normalization_negative_volume(self):
        dto = HistoricalCandleDTO(
            timestamp=datetime(2024, 2, 7, 10, 0, tzinfo=UTC),
            interval="1d",
            open=Decimal("2500.0"),
            high=Decimal("2550.0"),
            low=Decimal("2450.0"),
            close=Decimal("2500.0"),
            volume=-5,
            adjusted_close=None,
            source_provider="TEST",
        )
        with pytest.raises(DataQualityError, match="Negative volume.*encountered"):
            MarketDataNormalizer.validate_candle(dto)

    def test_quote_normalization_valid(self):
        now = timezone.now()
        dto = MarketQuoteDTO(
            symbol="RELIANCE",
            exchange="NSE",
            price=Decimal("2500.50"),
            change=Decimal("50.50"),
            change_percent=Decimal("2.06"),
            open=Decimal("2480.0"),
            high=Decimal("2520.0"),
            low=Decimal("2470.0"),
            close=Decimal("2500.50"),
            previous_close=Decimal("2450.0"),
            volume=500000,
            source_provider="TEST",
            source_type=SourceType.DIRECT,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=now,
            retrieved_at=now,
            measured_latency_ms=45,
        )
        validated = MarketDataNormalizer.validate_quote(dto)
        assert validated.price == Decimal("2500.50")
        assert validated.change == Decimal("50.50")
        assert validated.volume == 500000

    def test_quote_normalization_non_positive_price(self):
        now = timezone.now()
        dto = MarketQuoteDTO(
            symbol="RELIANCE",
            exchange="NSE",
            price=Decimal("0.0"),
            change=Decimal("0.0"),
            change_percent=Decimal("0.0"),
            open=Decimal("0.0"),
            high=Decimal("0.0"),
            low=Decimal("0.0"),
            close=Decimal("0.0"),
            previous_close=Decimal("100.0"),
            volume=0,
            source_provider="TEST",
            source_type=SourceType.DIRECT,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=now,
            retrieved_at=now,
        )
        with pytest.raises(DataQualityError, match="Invalid non-positive quote price"):
            MarketDataNormalizer.validate_quote(dto)


# ----------------------------------------------------------------------
# 2. Provider Adapter Tests
# ----------------------------------------------------------------------
class TestProviders:
    @patch("jugaad_data.nse.NSELive")
    def test_jugaad_get_quote(self, mock_nselive_cls, sample_instruments):
        mock_instance = MagicMock()
        mock_instance.stock_quote.return_value = {
            "priceInfo": {
                "lastPrice": 2900.0,
                "open": 2880.0,
                "change": 50.0,
                "pChange": 1.75,
                "close": 2900.0,
                "previousClose": 2850.0,
                "intraDayHighLow": {
                    "max": 2920.0,
                    "min": 2870.0,
                },
            },
            "securityWiseDP": {
                "quantityTraded": 1500000,
            },
        }
        mock_nselive_cls.return_value = mock_instance

        provider = JugaadDataProvider(request_delay_seconds=0.0)
        listing = sample_instruments["nse"]
        quote = provider.get_quote(listing)

        assert quote.symbol == "RELIANCE"
        assert quote.exchange == "NSE"
        assert quote.price == Decimal("2900.0")
        assert quote.source_provider == "JUGAAD"
        assert quote.source_type == SourceType.DIRECT

    @patch("yfinance.Ticker")
    def test_yahoo_get_quote(self, mock_ticker_cls, sample_instruments):
        mock_fast_info = MagicMock()
        mock_fast_info.last_price = 2910.0
        mock_fast_info.previous_close = 2860.0
        mock_fast_info.open = 2885.0
        mock_fast_info.day_high = 2925.0
        mock_fast_info.day_low = 2875.0
        mock_fast_info.last_volume = 1200000

        mock_ticker = MagicMock()
        mock_ticker.fast_info = mock_fast_info
        mock_ticker_cls.return_value = mock_ticker

        provider = YahooFinanceProvider()
        listing = sample_instruments["nse"]
        quote = provider.get_quote(listing)

        assert quote.symbol == "RELIANCE"
        assert quote.exchange == "NSE"
        assert quote.price == Decimal("2910.0")
        assert quote.source_provider == "YAHOO"
        # Yahoo Finance quotes are delayed and must be marked DELAYED
        assert quote.source_type == SourceType.DELAYED
        assert quote.configured_delay_minutes == 15

    def test_yahoo_symbol_formatting(self, sample_instruments):
        provider = YahooFinanceProvider()
        assert provider._to_yahoo_ticker(sample_instruments["nse"]) == "RELIANCE.NS"
        assert provider._to_yahoo_ticker(sample_instruments["bse"]) == "500325.BO"


# ----------------------------------------------------------------------
# 3. MarketDataService Tests
# ----------------------------------------------------------------------
@pytest.mark.django_db
class TestMarketDataService:
    def setup_method(self):
        cache.clear()

    @patch("integrations.market_data.providers.jugaad.adapter.JugaadDataProvider.get_quote")
    def test_get_quote_primary_success(self, mock_get_quote, sample_instruments):
        now = timezone.now()
        mock_get_quote.return_value = MarketQuoteDTO(
            symbol="RELIANCE",
            exchange="NSE",
            price=Decimal("2950.0"),
            change=Decimal("50.0"),
            change_percent=Decimal("1.72"),
            open=Decimal("2910.0"),
            high=Decimal("2960.0"),
            low=Decimal("2900.0"),
            close=Decimal("2950.0"),
            previous_close=Decimal("2900.0"),
            volume=2000000,
            source_provider="JUGAAD",
            source_type=SourceType.DIRECT,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=now,
            retrieved_at=now,
            measured_latency_ms=120,
        )

        listing = sample_instruments["nse"]
        quote = MarketDataService.get_quote(listing)

        assert quote.price == Decimal("2950.0")
        assert quote.source_provider == "JUGAAD"
        assert MarketQuote.objects.filter(listing=listing).count() == 1

        # Second call within TTL should return CACHED quote from cache
        quote_cached = MarketDataService.get_quote(listing)
        assert quote_cached.freshness_status == FreshnessStatus.CACHED.value

    @patch("integrations.market_data.providers.yahoo.adapter.YahooFinanceProvider.get_quote")
    @patch("integrations.market_data.providers.jugaad.adapter.JugaadDataProvider.get_quote")
    def test_get_quote_fallback_to_yahoo(self, mock_jugaad, mock_yahoo, sample_instruments):
        # Primary fails
        mock_jugaad.side_effect = ProviderConnectionError("NSE API Timeout")

        # Fallback succeeds
        now = timezone.now()
        mock_yahoo.return_value = MarketQuoteDTO(
            symbol="RELIANCE",
            exchange="NSE",
            price=Decimal("2945.0"),
            change=Decimal("45.0"),
            change_percent=Decimal("1.55"),
            open=Decimal("2910.0"),
            high=Decimal("2960.0"),
            low=Decimal("2900.0"),
            close=Decimal("2945.0"),
            previous_close=Decimal("2900.0"),
            volume=1800000,
            source_provider="YAHOO",
            source_type=SourceType.DELAYED,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=now,
            retrieved_at=now,
            measured_latency_ms=350,
            configured_delay_minutes=15,
        )

        listing = sample_instruments["nse"]
        quote = MarketDataService.get_quote(listing, force_refresh=True)

        assert quote.source_provider == "YAHOO"
        assert quote.source_type == SourceType.DELAYED.value
        # Quality issue should have been logged for primary failure
        assert DataQualityIssue.objects.filter(listing=listing, issue_type="PROVIDER_DISCREPANCY").exists()

    @patch("integrations.market_data.providers.yahoo.adapter.YahooFinanceProvider.get_historical_candles")
    @patch("integrations.market_data.providers.jugaad.adapter.JugaadDataProvider.get_historical_candles")
    def test_get_historical_candles_and_backfill(self, mock_jugaad_hist, mock_yahoo_hist, sample_instruments):
        mock_jugaad_hist.side_effect = ProviderConnectionError("NSE API Unavailable")
        listing = sample_instruments["nse"]
        start_date = date(2024, 2, 1)
        end_date = date(2024, 2, 3)

        mock_yahoo_hist.return_value = [
            HistoricalCandleDTO(
                timestamp=datetime(2024, 2, 1, 10, 0, tzinfo=UTC),
                interval="1d",
                open=Decimal("2800.0"),
                high=Decimal("2850.0"),
                low=Decimal("2790.0"),
                close=Decimal("2840.0"),
                volume=1000000,
                adjusted_close=Decimal("2840.0"),
                source_provider="YAHOO",
            ),
            HistoricalCandleDTO(
                timestamp=datetime(2024, 2, 2, 10, 0, tzinfo=UTC),
                interval="1d",
                open=Decimal("2840.0"),
                high=Decimal("2890.0"),
                low=Decimal("2830.0"),
                close=Decimal("2880.0"),
                volume=1100000,
                adjusted_close=Decimal("2880.0"),
                source_provider="YAHOO",
            ),
        ]

        # 1. Fetch missing candles: writes to DB
        candles = MarketDataService.get_historical_candles(listing, start_date, end_date)
        assert len(candles) == 2
        assert HistoricalCandle.objects.filter(listing=listing).count() == 2

        # 2. Subsequent query retrieves from DB without invoking provider again
        mock_yahoo_hist.reset_mock()
        candles_db = MarketDataService.get_historical_candles(listing, start_date, end_date)
        assert len(candles_db) == 2
        mock_yahoo_hist.assert_not_called()


# ----------------------------------------------------------------------
# 4. Data Sources UI View & HTMX Tests
# ----------------------------------------------------------------------
@pytest.mark.django_db
class TestDataSourcesView:
    def test_data_sources_full_page_load(self):
        client = Client()
        url = reverse("settings_app:data_sources")
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Data Sources &amp; Provider Health" in content or "Data Sources & Provider Health" in content
        # Verify providers rendered
        assert "Jugaad-Data" in content
        assert "Yahoo Finance" in content
        # Verify persistent shell elements present
        assert "sidebar" in content.lower()

    def test_data_sources_htmx_partial_load(self):
        client = Client()
        url = reverse("settings_app:data_sources")
        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        # Should return partial content, not base shell
        assert "<!DOCTYPE html>" not in content
        assert "Jugaad-Data" in content
        assert "Yahoo Finance" in content


# ----------------------------------------------------------------------
# 5. Celery Background Tasks Tests
# ----------------------------------------------------------------------
@pytest.mark.django_db
class TestCeleryTasks:
    @patch("integrations.market_data.health.ProviderHealthMonitor.check_all_providers")
    def test_monitor_provider_health_task(self, mock_check):
        mock_check.return_value = {"JUGAAD": "HEALTHY", "YAHOO": "HEALTHY"}
        result = monitor_provider_health_task()
        assert result == {"JUGAAD": "HEALTHY", "YAHOO": "HEALTHY"}
        mock_check.assert_called_once()

    def test_ingest_bhavcopy_task_skips_holiday(self):
        # Republic Day 2024-01-26 is a holiday
        result = ingest_daily_bhavcopy_task(target_date_str="2024-01-26")
        assert result["status"] == "skipped"
        assert result["reason"] == "holiday_or_weekend"


# ----------------------------------------------------------------------
# 6. Management Commands Tests
# ----------------------------------------------------------------------
@pytest.mark.django_db
class TestManagementCommands:
    def test_seed_instruments_command(self):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("seed_instruments", stdout=out)
        output = out.getvalue()
        assert "Exchanges verified: NSE, BSE" in output
        assert Instrument.objects.filter(isin="INE002A01018").exists()

    @patch("services.market_data.service.MarketDataService.get_quote")
    def test_import_market_data_command(self, mock_get_quote, sample_instruments):
        from io import StringIO

        from django.core.management import call_command
        mock_get_quote.return_value = MarketQuote(
            listing=sample_instruments["nse"],
            price=Decimal("2950.0"),
            change=Decimal("50.0"),
            change_percent=Decimal("1.72"),
            open=Decimal("2900.0"),
            high=Decimal("2960.0"),
            low=Decimal("2890.0"),
            close=Decimal("2950.0"),
            previous_close=Decimal("2900.0"),
            volume=1000000,
            source_provider="JUGAAD",
            source_type=SourceType.DIRECT,
            freshness_status=FreshnessStatus.FRESH,
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        out = StringIO()
        call_command("import_market_data", symbol="RELIANCE", exchange="NSE", stdout=out)
        output = out.getvalue()
        assert "[RELIANCE] Price: ₹2950.0" in output
        assert "Finished. Success: 1, Errors: 0" in output

