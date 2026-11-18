"""
Tests for Technical and Fundamental Analysis Overview hubs and background tasks.
"""
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from apps.technical_analysis.tasks import (
    calculate_all_active_indicators_task,
    calculate_technical_indicators_task,
)


@pytest.fixture
def sample_research_data(db):
    nse = Exchange.objects.create(code="NSE", name="National Stock Exchange")
    inst = Instrument.objects.create(
        isin="INE002A01018",
        legal_name="Reliance Industries Limited",
        display_name="Reliance",
        sector="Energy",
        industry="Refineries",
        market_cap_category="LARGE",
    )
    listing = ExchangeListing.objects.create(
        instrument=inst,
        exchange=nse,
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        is_primary=True,
        is_tradeable=True,
    )

    now = timezone.now() - timedelta(days=26)
    for i in range(25):
        HistoricalCandle.objects.create(
            listing=listing,
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

    TechnicalIndicatorSnapshot.objects.create(
        listing=listing,
        interval="1d",
        timestamp=now + timedelta(days=24),
        sma_20=Decimal("2510.0"),
        rsi_14=Decimal("62.5"),
        trend_signal="BULLISH",
        breakout_signal="RESISTANCE_BREAKOUT",
        calculation_version="tech-v2.0.0",
    )

    FundamentalSnapshot.objects.create(
        instrument=inst,
        pe_ratio=Decimal("24.5"),
        sector_pe=Decimal("22.0"),
        roe=Decimal("15.2"),
        debt_to_equity=Decimal("0.40"),
        overall_score=82,
        growth_score=75,
        profitability_score=85,
        valuation_score=72,
        financial_health_score=80,
        calculation_version="fund-v2.0.0",
    )

    return {"listing": listing, "instrument": inst}


@pytest.mark.django_db
class TestResearchOverviewHubs:
    def test_technical_overview_full_and_htmx(self, sample_research_data):
        client = Client()
        url = reverse("technical_analysis:overview")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Technical Analysis Intelligence" in content
        assert "RELIANCE" in content
        assert "sidebar" in content.lower()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "Technical Analysis Intelligence" in resp_htmx.content.decode()

    def test_fundamental_overview_full_and_htmx(self, sample_research_data):
        client = Client()
        url = reverse("fundamental_analysis:overview")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Fundamental Analysis & Valuation Hub" in content
        assert "Reliance" in content
        assert "sidebar" in content.lower()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()
        assert "Fundamental Analysis & Valuation Hub" in resp_htmx.content.decode()


@pytest.mark.django_db
class TestTechnicalTasksAndCommands:
    def test_calculate_technical_indicators_task(self, sample_research_data):
        listing = sample_research_data["listing"]
        result = calculate_technical_indicators_task(str(listing.id))
        assert result["status"] == "success"
        assert result["symbol"] == "RELIANCE"
        assert result["snapshots_created"] == 25

    @patch("apps.technical_analysis.tasks.calculate_technical_indicators_task.delay")
    def test_calculate_all_active_indicators_task(self, mock_delay, sample_research_data):
        result = calculate_all_active_indicators_task()
        assert result["status"] == "queued"
        assert result["tasks_dispatched"] >= 1
        mock_delay.assert_called()

    def test_seed_stock_research_command(self, sample_research_data):
        out = StringIO()
        call_command("seed_stock_research", stdout=out)
        output = out.getvalue()
        assert "Stock research data successfully seeded!" in output
