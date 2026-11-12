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

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
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
        calculation_version="tech-v1.0.0",
    )

    # Fundamental Snapshot
    FundamentalSnapshot.objects.create(
        instrument=inst_rel,
        pe_ratio=Decimal("24.5"),
        sector_pe=Decimal("22.0"),
        roe=Decimal("14.5"),
        debt_to_equity=Decimal("0.40"),
        overall_score=78,
        calculation_version="fund-v1.0.0",
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

    def test_stock_detail_full_and_htmx(self, seeded_stocks):
        client = Client()
        url = reverse("stocks:stock_detail", kwargs={"symbol": "RELIANCE"})

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Reliance Industries Limited" in content
        assert "tech-v1.0.0" in content
        assert "fund-v1.0.0" in content
        assert "stock-chart-canvas" in content

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "Reliance Industries Limited" in resp_htmx.content.decode()

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
