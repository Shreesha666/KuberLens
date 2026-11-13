"""
Automated tests for IPO Intelligence Module (Phase A).
Validates models, lifecycle calculations, views, HTMX partials, and seed data.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ipo.models import IPOMaster, IPOStatus, IssueType
from services.ipo.lifecycle import get_status_badge_class, get_timeline_milestones


@pytest.fixture
def ipo_dataset(db):
    """Creates a sample dataset of Mainboard and SME IPOs in different lifecycle stages."""
    today = timezone.now().date()
    live_ipo = IPOMaster.objects.create(
        symbol="TESTLIVE",
        company_name="Test Live Energies Limited",
        isin="INE00TEST111",
        issue_type=IssueType.MAINBOARD,
        exchange="BOTH",
        sector="Utilities",
        industry="Solar Power",
        status=IPOStatus.LIVE,
        open_date=today - timedelta(days=1),
        close_date=today + timedelta(days=2),
        allotment_date=today + timedelta(days=4),
        listing_date=today + timedelta(days=7),
        price_band_min=Decimal("100.00"),
        price_band_max=Decimal("110.00"),
        lot_size=100,
        min_investment=Decimal("11000.00"),
        total_issue_size_cr=Decimal("500.00"),
        fresh_issue_cr=Decimal("500.00"),
        offer_for_sale_cr=Decimal("0.00"),
    )

    upcoming_ipo = IPOMaster.objects.create(
        symbol="TESTUPCOMING",
        company_name="Test Upcoming Logistics Limited",
        isin="INE00TEST222",
        issue_type=IssueType.MAINBOARD,
        exchange="NSE",
        sector="Logistics",
        status=IPOStatus.UPCOMING,
        open_date=today + timedelta(days=5),
        close_date=today + timedelta(days=8),
        price_band_min=Decimal("200.00"),
        price_band_max=Decimal("220.00"),
        lot_size=50,
        total_issue_size_cr=Decimal("300.00"),
    )

    sme_ipo = IPOMaster.objects.create(
        symbol="TESTSME",
        company_name="Test SME Tech Limited",
        isin="INE00TEST333",
        issue_type=IssueType.SME,
        exchange="BSE",
        sector="Technology",
        status=IPOStatus.LISTED,
        open_date=today - timedelta(days=20),
        close_date=today - timedelta(days=17),
        listing_date=today - timedelta(days=12),
        issue_price=Decimal("75.00"),
        lot_size=1600,
        total_issue_size_cr=Decimal("12.00"),
        listing_day_open=Decimal("120.00"),
        listing_day_close=Decimal("125.00"),
        listing_day_gain_percent=Decimal("66.67"),
    )

    return {
        "live": live_ipo,
        "upcoming": upcoming_ipo,
        "sme": sme_ipo,
    }


@pytest.mark.django_db
class TestIPOIntelligenceModule:
    """Tests for IPO models, lifecycle domain logic, and views."""

    def test_ipo_master_properties(self, ipo_dataset):
        live = ipo_dataset["live"]
        assert live.price_band_display == "₹100 - ₹110"
        assert live.effective_upper_price == Decimal("110.00")
        assert live.calculated_min_investment == Decimal("11000.00")
        assert live.is_currently_open is True

        sme = ipo_dataset["sme"]
        assert sme.price_band_display == "₹75.00"
        assert sme.effective_upper_price == Decimal("75.00")
        assert sme.calculated_min_investment == Decimal("120000.00")

    def test_lifecycle_milestones_and_badges(self, ipo_dataset):
        live = ipo_dataset["live"]
        milestones = get_timeline_milestones(live)
        assert len(milestones) == 5
        keys = [m["key"] for m in milestones]
        assert keys == ["drhp", "open", "close", "allotment", "listing"]

        # Check badges
        assert "bg-success" in get_status_badge_class("LIVE")
        assert "bg-primary" in get_status_badge_class("UPCOMING")
        assert "bg-dark" in get_status_badge_class("LISTED")

    def test_ipo_dashboard_view_full_page_and_htmx(self, client: Client, ipo_dataset):
        url = reverse("ipo:dashboard")

        # Full page shell
        resp = client.get(url)
        assert resp.status_code == 200
        assert "main-content" in resp.content.decode("utf-8")
        assert "IPO Intelligence Centre" in resp.content.decode("utf-8")
        assert "TESTLIVE" in resp.content.decode("utf-8")

        # HTMX partial swap
        htmx_resp = client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        assert "<!DOCTYPE html>" not in htmx_resp.content.decode("utf-8")
        assert "Spotlight" in htmx_resp.content.decode("utf-8")

    def test_ipo_issues_list_view_and_filtering(self, client: Client, ipo_dataset):
        url = reverse("ipo:issues")

        # Default list
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "TESTLIVE" in content
        assert "TESTUPCOMING" in content
        assert "TESTSME" in content

        # Filter by Tab: live
        resp_live = client.get(f"{url}?tab=live")
        content_live = resp_live.content.decode("utf-8")
        assert "TESTLIVE" in content_live

        # Filter by Segment: SME
        resp_sme = client.get(f"{url}?type=SME")
        content_sme = resp_sme.content.decode("utf-8")
        assert "TESTSME" in content_sme
        assert "TESTLIVE" not in content_sme

        # Search Query
        resp_search = client.get(f"{url}?q=Logistics")
        content_search = resp_search.content.decode("utf-8")
        assert "TESTUPCOMING" in content_search
        assert "TESTLIVE" not in content_search

    def test_ipo_calendar_view(self, client: Client, ipo_dataset):
        url = reverse("ipo:calendar")

        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Primary Market Events Calendar" in content
        assert "TESTLIVE" in content
        assert "TESTUPCOMING" in content

        # HTMX request
        htmx_resp = client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        assert "<!DOCTYPE html>" not in htmx_resp.content.decode("utf-8")

    def test_ipo_detail_view(self, client: Client, ipo_dataset):
        # Valid detail view
        url = reverse("ipo:detail", kwargs={"symbol": "TESTLIVE"})
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Test Live Energies Limited" in content
        assert "₹100 - ₹110" in content
        assert "₹500.0 Cr" in content

        # HTMX partial
        htmx_resp = client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        assert "Test Live Energies Limited" in htmx_resp.content.decode("utf-8")

        # 404 on nonexistent symbol
        resp_404 = client.get(reverse("ipo:detail", kwargs={"symbol": "NONEXISTENT"}))
        assert resp_404.status_code == 404

    def test_seed_ipo_data_command(self):
        """Verifies that seed_ipo_data runs idempotently and populates canonical records."""
        call_command("seed_ipo_data")
        assert IPOMaster.objects.filter(symbol="SWIGGY").exists()
        assert IPOMaster.objects.filter(symbol="WAAREEENER").exists()
        assert IPOMaster.objects.filter(symbol="HYUNDAI").exists()
        assert IPOMaster.objects.filter(symbol="BAJAJHFL").exists()
        assert IPOMaster.objects.filter(symbol="NTPCGREEN").exists()
        assert IPOMaster.objects.filter(symbol="BOSSPACK").exists()
