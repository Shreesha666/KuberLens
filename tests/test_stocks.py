"""
Integration & UI tests for Stock Research, Autocomplete Search, and Detail Views.
Verifies full-page vs HTMX partial rendering, chart JSON endpoints, and search capabilities.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from apps.portfolio.models import Portfolio
from apps.technical_analysis.models import TechnicalIndicatorSnapshot


@pytest.fixture
def seeded_stocks(db):
    nse = Exchange.objects.create(code="NSE", name="National Stock Exchange")
    Exchange.objects.create(code="BSE", name="Bombay Stock Exchange")

    inst_rel = Instrument.objects.create(
        isin="INE002A01018",
        legal_name="Reliance Industries Limited",
        display_name="Reliance",
        sector="Energy",
        industry="Refineries",
        market_cap_category="LARGE",
    )
    rel_listing = ExchangeListing.objects.create(
        instrument=inst_rel,
        exchange=nse,
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        is_primary=True,
        is_tradeable=True,
    )

    inst_tcs = Instrument.objects.create(
        isin="INE467B01029",
        legal_name="Tata Consultancy Services Limited",
        display_name="TCS",
        sector="Information Technology",
        industry="IT Services",
        market_cap_category="LARGE",
    )
    tcs_listing = ExchangeListing.objects.create(
        instrument=inst_tcs,
        exchange=nse,
        symbol="TCS",
        trading_symbol="TCS",
        is_primary=True,
        is_tradeable=True,
    )

    inst_bandhan = Instrument.objects.create(
        isin="INE528058670",
        legal_name="Bandhan Bank Limited",
        display_name="Bandhan Bank",
        sector="Financial Services",
        industry="Private Sector Bank",
        market_cap_category="MID",
    )
    ExchangeListing.objects.create(
        instrument=inst_bandhan,
        exchange=nse,
        symbol="BANDHANBNK",
        trading_symbol="BANDHANBNK",
        is_primary=True,
        is_tradeable=True,
    )

    inst_urban = Instrument.objects.create(
        isin="INE0W9Y01014",
        legal_name="Urban Company Limited",
        display_name="Urban Company",
        sector="Technology",
        industry="Consumer Tech",
        market_cap_category="MID",
    )
    ExchangeListing.objects.create(
        instrument=inst_urban,
        exchange=nse,
        symbol="URBANCO",
        trading_symbol="URBANCO",
        is_primary=True,
        is_tradeable=True,
    )

    # Historical candles for RELIANCE
    now = timezone.now() - timedelta(days=26)
    for i in range(25):
        HistoricalCandle.objects.create(
            listing=rel_listing,
            timestamp=now + timedelta(days=i),
            interval="1d",
            open=Decimal("2500.0"),
            high=Decimal("2550.0"),
            low=Decimal("2480.0"),
            close=Decimal("2520.0"),
            volume=1000000,
            adjusted_close=Decimal("2520.0"),
            source_provider="TEST",
        )

    # Technical Snapshot
    TechnicalIndicatorSnapshot.objects.create(
        listing=rel_listing,
        interval="1d",
        timestamp=now + timedelta(days=24),
        sma_20=Decimal("2510.0"),
        sma_50=Decimal("2490.0"),
        rsi_14=Decimal("62.5"),
        trend_signal="BULLISH",
        calculation_version="tech-v2.0.0",
    )

    # Fundamental Snapshot
    FundamentalSnapshot.objects.create(
        instrument=inst_rel,
        pe_ratio=Decimal("24.5"),
        sector_pe=Decimal("22.0"),
        roe=Decimal("14.5"),
        debt_to_equity=Decimal("0.40"),
        dividend_yield=Decimal("2.40"),
        overall_score=78,
        calculation_version="fund-v2.0.0",
    )

    # MarketQuote for RELIANCE
    now_ts = timezone.now()
    MarketQuote.objects.create(
        listing=rel_listing,
        price=Decimal("2850.00"),
        open=Decimal("2800.00"),
        high=Decimal("2860.00"),
        low=Decimal("2790.00"),
        close=Decimal("2850.00"),
        previous_close=Decimal("2820.00"),
        change=Decimal("30.00"),
        change_percent=Decimal("1.06"),
        volume=1500000,
        source_provider="YAHOO",
        source_type="DELAYED",
        freshness_status="FRESH",
        source_timestamp=now_ts,
        retrieved_at=now_ts,
    )

    return {"rel": rel_listing, "tcs": tcs_listing}


@pytest.mark.django_db
class TestStockViews:
    def test_search_by_symbol_json(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:stock_search") + "?q=REL"
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["symbol"] == "RELIANCE"

    def test_search_by_company_name_and_isin(self, seeded_stocks):
        client = Client()
        # Search by company name
        res_name = client.get(reverse("stocks:stock_search") + "?q=Consultancy")
        assert res_name.status_code == 200
        assert res_name.json()["results"][0]["symbol"] == "TCS"

        # Search by ISIN
        res_isin = client.get(reverse("stocks:stock_search") + "?q=INE002A01018")
        assert res_isin.status_code == 200
        assert res_isin.json()["results"][0]["symbol"] == "RELIANCE"

    def test_search_typo_tolerance_bandhan_bank(self, seeded_stocks):
        client = Client()
        # Typo: 'badhan bank' (missing 'n')
        res_typo = client.get(reverse("stocks:stock_search") + "?q=badhan+bank")
        assert res_typo.status_code == 200
        data = res_typo.json()["results"]
        assert len(data) >= 1
        assert data[0]["symbol"] == "BANDHANBNK"

        # Typo: 'badhan'
        res_single = client.get(reverse("stocks:stock_search") + "?q=badhan")
        assert res_single.status_code == 200
        data_single = res_single.json()["results"]
        assert len(data_single) >= 1
        assert data_single[0]["symbol"] == "BANDHANBNK"

    def test_search_urban_company(self, seeded_stocks):
        client = Client()
        # Urban company
        res = client.get(reverse("stocks:stock_search") + "?q=urban+company")
        assert res.status_code == 200
        data = res.json()["results"]
        assert len(data) >= 1
        assert data[0]["symbol"] == "URBANCO"

    def test_search_multi_word_token_conjunction(self, seeded_stocks):
        client = Client()
        # Reversed words: 'bank bandhan'
        res = client.get(reverse("stocks:stock_search") + "?q=bank+bandhan")
        assert res.status_code == 200
        data = res.json()["results"]
        assert len(data) >= 1
        assert data[0]["symbol"] == "BANDHANBNK"

    def test_search_htmx_partial_response(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:stock_search") + "?q=REL"
        response = client.get(url, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        content = response.content.decode()
        assert "RELIANCE" in content
        assert "list-group-item" in content

    def test_stock_list_full_shell_and_htmx(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:stock_list")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "RELIANCE" in resp_full.content.decode()
        assert "TCS" in resp_full.content.decode()
        assert "sidebar" in resp_full.content.decode().lower()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "RELIANCE" in resp_htmx.content.decode()

    def test_stock_detail_full_and_htmx(self, seeded_stocks, monkeypatch):
        # Isolate from external network calls during unit test
        from services.market_data.service import MarketDataService
        from services.fundamentals.analyzer import FundamentalAnalyzer
        monkeypatch.setattr(
            MarketDataService,
            "get_quote",
            lambda listing: MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first(),
        )
        monkeypatch.setattr(
            FundamentalAnalyzer,
            "sync_dividend_from_yahoo",
            lambda *args, **kwargs: (None, None),
        )
        client = Client()
        url = reverse("stocks:stock_detail", kwargs={"symbol": "RELIANCE"})

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Reliance Industries Limited" in content
        assert "tech-v2.0.0" in content
        assert "fund-v2.0.0" in content
        assert "stock-chart-canvas" in content
        assert "Existing Holder Strategy" in content
        assert "New Prospective Investor" in content
        assert "Optimal Entry Zone" in content
        assert "68.40" in content  # ₹68.40 (2.40%) dividend amount per share
        assert "2.40%" in content
        assert "Dividend History (5Y)" in content
        assert "dividends-pane" in content

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "Reliance Industries Limited" in resp_htmx.content.decode()
        assert "Dividend History (5Y)" in resp_htmx.content.decode()
        assert "Existing Holder Strategy" in resp_htmx.content.decode()
        assert "New Prospective Investor" in resp_htmx.content.decode()

    def test_stock_detail_with_active_holding(self, seeded_stocks):
        client = Client()
        user = CustomUser.objects.create_user(
            username="stockholdertest", email="stockholder@example.com", password="pass"
        )
        client.force_login(user)

        portfolio = Portfolio.objects.create(user=user, name="Main Portfolio", is_default=True)
        rel_listing = ExchangeListing.objects.get(symbol="RELIANCE")

        Holding.objects.create(
            portfolio=portfolio,
            listing=rel_listing,
            total_quantity=50,
            average_buy_price=Decimal("2400.00"),
            invested_amount=Decimal("120000.00"),
            current_price=Decimal("2520.00"),
            current_value=Decimal("126000.00"),
            unrealised_pnl=Decimal("6000.00"),
            unrealised_pnl_percent=Decimal("5.00"),
        )

        url = reverse("stocks:stock_detail", kwargs={"symbol": "RELIANCE"})
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "Existing Holder Strategy" in content
        assert "50 shares" in content
        assert "View In Holdings" in content
        assert "New Prospective Investor" in content
        assert "data-kpi-counter" in content

    def test_stock_quote_partial_endpoint(self, seeded_stocks, monkeypatch):
        from services.market_data.service import MarketDataService
        monkeypatch.setattr(
            MarketDataService,
            "get_quote",
            lambda listing, force_refresh=False: MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first(),
        )
        client = Client()
        url = reverse("stocks:stock_quote_partial", kwargs={"symbol": "RELIANCE"})
        res = client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "stock-quote-container" in content
        assert "data-stock-quote-widget" in content
        assert "data-silent-refresh" in content
        assert "data-kpi-counter" in content
        assert "RELIANCE" in content

    def test_stock_detail_nonexistent_returns_404(self):
        client = Client()
        url = reverse("stocks:stock_detail", kwargs={"symbol": "UNKNOWN123"})
        response = client.get(url)
        assert response.status_code == 404

    def test_stock_chart_data_endpoint(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:stock_chart_data", kwargs={"symbol": "RELIANCE"})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "RELIANCE"
        assert len(data["candles"]) == 25
        assert "open" in data["candles"][0]
        assert "close" in data["candles"][0]
        assert "sma20" in data["candles"][-1]
        assert "ema20" in data["candles"][-1]
        assert "ema9" in data["candles"][-1]
        assert "vwap" in data["candles"][-1]
        assert "supertrend" in data["candles"][-1]
        assert "sar" in data["candles"][-1]
        assert "rsi14" in data["candles"][-1]
        assert "stoch_k" in data["candles"][-1]
        assert "atr14" in data["candles"][-1]
        assert "macd_line" in data["candles"][-1]
        assert "levels" in data
        assert "stop_loss" in data["levels"]
        assert "target_1" in data["levels"]
        assert "confluence_score" in data["levels"]
        assert "fibonacci" in data
        assert "level_618" in data["fibonacci"]

    def test_sector_analysis_view_full_and_htmx(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:sector_analysis")

        # Full page direct load
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Sector Analysis" in content
        assert "Energy" in content
        assert "Information Technology" in content

        # HTMX partial swap
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "Sector Performance & Valuation Matrix" in resp_htmx.content.decode()

    def test_sector_analysis_filtered_sector(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:sector_analysis") + "?sector=Energy"

        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Constituent Stocks in Energy" in content
        assert "RELIANCE" in content

    def test_five_year_dividend_history_retrieval(self, monkeypatch):
        import pandas as pd
        from datetime import datetime, timezone as dt_timezone
        from services.fundamentals.analyzer import FundamentalAnalyzer

        # Mock yfinance Ticker dividends
        mock_tz = dt_timezone.utc
        dates = [
            datetime(2026, 8, 14, tzinfo=mock_tz),
            datetime(2026, 3, 12, tzinfo=mock_tz),
            datetime(2025, 12, 18, tzinfo=mock_tz),
        ]
        mock_divs = pd.Series([1.25, 2.00, 5.00], index=pd.to_datetime(dates))

        class MockTicker:
            def __init__(self, ticker):
                self.dividends = mock_divs
                self.history_called = False

            def history(self, period="5y"):
                return pd.DataFrame(
                    {"Close": [100.0, 100.0, 100.0]},
                    index=pd.to_datetime(dates)
                )

        import yfinance as yf
        monkeypatch.setattr(yf, "Ticker", MockTicker)

        history, summary = FundamentalAnalyzer.get_five_year_dividend_history("TESTSTOCK", current_price=100.0)
        assert len(history) == 3
        assert summary["total_5y_count"] == 3
        assert summary["total_5y_payout"] == Decimal("8.25")
        assert summary["paying_years"] >= 2
        assert history[0]["amount"] == Decimal("1.25")
        assert history[0]["type"] == "FINAL"  # August is Final
        assert history[1]["type"] == "INTERIM"  # March is Interim

