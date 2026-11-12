"""
Tests for Stock Screener Module and Engine.
Verifies multi-variable filtering (technical, fundamental, market cap),
human-readable match reason explanations, preset configuration saving,
CSV result export, and HTMX dual-mode views.
"""
import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.screener.models import ScreenerConfiguration
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.screener.engine import ScreenerEngine

User = get_user_model()


@pytest.fixture
def screener_data(db):
    user = User.objects.create_user(
        username="screen_tester",
        email="screen@example.com",
        password="password123",
    )
    exchange = Exchange.objects.create(code="NSE", name="NSE")

    # 1. Quality Bluechip Stock: RELIANCE
    inst1 = Instrument.objects.create(
        isin="INE002A01018",
        display_name="Reliance Industries",
        legal_name="Reliance Industries Limited",
        sector="Energy",
        market_cap_category="LARGE",
    )
    listing1 = ExchangeListing.objects.create(instrument=inst1, exchange=exchange, symbol="RELIANCE", is_tradeable=True)
    now = timezone.now()
    MarketQuote.objects.create(
        listing=listing1,
        price=Decimal("2800.00"),
        open=Decimal("2780.00"),
        high=Decimal("2820.00"),
        low=Decimal("2775.00"),
        close=Decimal("2800.00"),
        previous_close=Decimal("2750.00"),
        change=Decimal("50.00"),
        change_percent=Decimal("1.82"),
        volume=1500000,
        source_provider="YAHOO",
        source_type="DELAYED",
        freshness_status="FRESH",
        source_timestamp=now,
        retrieved_at=now,
    )
    TechnicalIndicatorSnapshot.objects.create(
        listing=listing1,
        timestamp=now,
        rsi_14=Decimal("62.5"),
        trend_signal="BULLISH",
        sma_20=Decimal("2750.00"),
        sma_50=Decimal("2680.00"),
        sma_200=Decimal("2500.00"),
    )
    FundamentalSnapshot.objects.create(
        instrument=inst1,
        calculated_at=now,
        overall_score=78,
        pe_ratio=Decimal("22.5"),
        roe=Decimal("18.4"),
        roce=Decimal("19.2"),
        debt_to_equity=Decimal("0.45"),
        revenue_growth_yoy=Decimal("16.8"),
    )

    # 2. Oversold Small Cap Stock: TINY
    inst2 = Instrument.objects.create(
        isin="INE999Z01011",
        display_name="Tiny Tech",
        legal_name="Tiny Tech Limited",
        sector="Technology",
        market_cap_category="SMALL",
    )
    listing2 = ExchangeListing.objects.create(instrument=inst2, exchange=exchange, symbol="TINY", is_tradeable=True)
    MarketQuote.objects.create(
        listing=listing2,
        price=Decimal("120.00"),
        open=Decimal("125.00"),
        high=Decimal("126.00"),
        low=Decimal("119.00"),
        close=Decimal("120.00"),
        previous_close=Decimal("128.00"),
        change=Decimal("-8.00"),
        change_percent=Decimal("-6.25"),
        volume=200000,
        source_provider="YAHOO",
        source_type="DELAYED",
        freshness_status="FRESH",
        source_timestamp=now,
        retrieved_at=now,
    )
    TechnicalIndicatorSnapshot.objects.create(
        listing=listing2,
        timestamp=now,
        rsi_14=Decimal("28.0"),
        trend_signal="BEARISH",
        sma_20=Decimal("135.00"),
        sma_50=Decimal("142.00"),
        sma_200=Decimal("160.00"),
    )
    FundamentalSnapshot.objects.create(
        instrument=inst2,
        calculated_at=now,
        overall_score=42,
        pe_ratio=Decimal("38.0"),
        roe=Decimal("8.5"),
        roce=Decimal("9.0"),
        debt_to_equity=Decimal("1.40"),
        revenue_growth_yoy=Decimal("-4.2"),
    )

    return {
        "user": user,
        "listing1": listing1,
        "listing2": listing2,
    }


@pytest.mark.django_db
class TestScreenerEngine:
    def test_filter_by_market_cap(self, screener_data):
        results_large = ScreenerEngine.run_screen({"market_cap": "LARGE"})
        symbols_large = [r["symbol"] for r in results_large]
        assert "RELIANCE" in symbols_large
        assert "TINY" not in symbols_large

        results_small = ScreenerEngine.run_screen({"market_cap": "SMALL"})
        symbols_small = [r["symbol"] for r in results_small]
        assert "TINY" in symbols_small
        assert "RELIANCE" not in symbols_small

    def test_filter_by_rsi_and_trend(self, screener_data):
        # Bullish momentum filter
        results_bullish = ScreenerEngine.run_screen({"trend_signal": "BULLISH", "min_rsi": "50"})
        symbols = [r["symbol"] for r in results_bullish]
        assert "RELIANCE" in symbols
        assert "TINY" not in symbols

        # Oversold filter (RSI <= 30)
        results_oversold = ScreenerEngine.run_screen({"max_rsi": "30"})
        symbols = [r["symbol"] for r in results_oversold]
        assert "TINY" in symbols
        assert "RELIANCE" not in symbols

    def test_filter_by_fundamentals(self, screener_data):
        # Value & Quality: P/E <= 25, ROE >= 15, Score >= 70
        filters = {
            "max_pe": "25.0",
            "min_roe": "15.0",
            "min_score": "70",
        }
        results = ScreenerEngine.run_screen(filters)
        symbols = [r["symbol"] for r in results]
        assert "RELIANCE" in symbols
        assert "TINY" not in symbols

    def test_match_reasons_explanation(self, screener_data):
        filters = {
            "market_cap": "LARGE",
            "trend_signal": "BULLISH",
            "min_score": "70",
        }
        results = ScreenerEngine.run_screen(filters)
        rel = next(r for r in results if r["symbol"] == "RELIANCE")
        reasons_text = " ".join(rel["reasons"])
        assert "Large Cap" in reasons_text
        assert "BULLISH" in reasons_text
        assert "Score 78 ≥ 70" in reasons_text

    def test_export_to_csv(self, screener_data):
        results = ScreenerEngine.run_screen({"market_cap": "LARGE"})
        csv_str = ScreenerEngine.export_to_csv(results)
        assert "RELIANCE" in csv_str
        assert "Symbol,Company Name,Sector" in csv_str


@pytest.mark.django_db
class TestScreenerViews:
    def test_screener_view_full_page_and_htmx(self, screener_data, client):
        client.force_login(screener_data["user"])
        url = reverse("screener:index")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "screener/screener.html" in [t.name for t in resp_full.templates]
        assert "Multi-Factor Stock Screener" in resp_full.content.decode()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "screener/partials/screener_partial.html" in [t.name for t in resp_htmx.templates]
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_preset_screener_execution(self, screener_data, client):
        client.force_login(screener_data["user"])
        url = f"{reverse('screener:index')}?preset=quality"
        resp = client.get(url)
        assert resp.status_code == 200
        assert "High Quality Moats" in resp.content.decode()
        assert "RELIANCE" in resp.content.decode()

    def test_save_and_delete_screener_configuration(self, screener_data, client):
        user = screener_data["user"]
        client.force_login(user)
        url = reverse("screener:index")

        post_data = {
            "name": "Custom RSI Value Scan",
            "description": "My custom screen",
            "filters_json": json.dumps({"min_rsi": "40", "max_pe": "30"}),
        }

        # Save config
        resp = client.post(url, data=post_data)
        assert resp.status_code == 302
        cfg = ScreenerConfiguration.objects.filter(user=user, name="Custom RSI Value Scan").first()
        assert cfg is not None
        assert cfg.filter_criteria["min_rsi"] == "40"

        # Delete config
        del_url = reverse("screener:delete_config", kwargs={"pk": cfg.id})
        del_resp = client.post(del_url)
        assert del_resp.status_code == 302
        assert not ScreenerConfiguration.objects.filter(id=cfg.id).exists()

    def test_screener_csv_export_endpoint(self, screener_data, client):
        client.force_login(screener_data["user"])
        url = f"{reverse('screener:export')}?preset=momentum"
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp["Content-Type"] == "text/csv"
        assert "attachment; filename=" in resp["Content-Disposition"]
        assert "RELIANCE" in resp.content.decode()
