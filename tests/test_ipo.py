"""
Automated tests for IPO Intelligence Module (Phase A & Phase B).
Validates models, lifecycle calculations, subscription analytics, fundamental research,
tabbed detail profiles, views, HTMX partials, and seed data.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ipo.models import (
    DocumentType,
    IPODocument,
    IPOFundamentals,
    IPOMaster,
    IPOStatus,
    IPOSubscriptionSnapshot,
    IssueType,
)
from services.ipo.lifecycle import get_status_badge_class, get_timeline_milestones
from services.ipo.research import compute_financial_metrics
from services.ipo.scoring import evaluate_ipo_scoring, get_radar_chart_geometry
from services.ipo.subscription import get_subscription_summary


@pytest.fixture
def ipo_dataset(db):
    """Creates a sample dataset of Mainboard and SME IPOs with fundamentals and subscription snapshots."""
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
        fresh_issue_cr=Decimal("350.00"),
        offer_for_sale_cr=Decimal("150.00"),
    )

    # Seed multi-day subscription snapshots for live IPO
    IPOSubscriptionSnapshot.objects.create(
        ipo=live_ipo,
        day_number=1,
        qib_subscription=Decimal("0.50"),
        nii_subscription=Decimal("1.20"),
        retail_subscription=Decimal("2.00"),
        total_subscription=Decimal("1.10"),
        total_applications=150000,
    )
    IPOSubscriptionSnapshot.objects.create(
        ipo=live_ipo,
        day_number=2,
        qib_subscription=Decimal("5.00"),
        nii_subscription=Decimal("12.50"),
        retail_subscription=Decimal("6.20"),
        total_subscription=Decimal("7.30"),
        total_applications=480000,
    )

    # Seed fundamentals for live IPO
    IPOFundamentals.objects.create(
        ipo=live_ipo,
        revenue_fy_prev2=Decimal("100.00"),
        revenue_fy_prev1=Decimal("150.00"),
        revenue_fy_latest=Decimal("225.00"),
        ebitda_latest=Decimal("45.00"),
        pat_latest=Decimal("25.00"),
        net_worth=Decimal("300.00"),
        total_borrowings=Decimal("90.00"),
        cash_flow_operations=Decimal("35.00"),
        free_cash_flow=Decimal("15.00"),
        roe_percent=Decimal("18.50"),
        roce_percent=Decimal("22.00"),
        post_issue_pe=Decimal("24.00"),
        peer_industry_pe=Decimal("35.00"),
        peer_comparison_data=[
            {"name": "Peer Energy A", "pe": 34.0, "pb": 4.5, "roe": 14.0, "ev_ebitda": 16.0, "revenue_cr": 1200.0},
        ],
        key_strengths="Robust renewable pipeline and established utility contracts.",
        key_risks="Grid curtailment risk and interest rate sensitivity.",
        use_of_proceeds="Solar project expansion in Rajasthan.",
    )

    # Seed document for live IPO
    IPODocument.objects.create(
        ipo=live_ipo,
        doc_type=DocumentType.RHP,
        title="Test Live Energies - Red Herring Prospectus",
        file_url="https://example.com/rhp.pdf",
        filing_date=today - timedelta(days=5),
        file_size_mb=Decimal("12.50"),
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
        fresh_issue_cr=Decimal("100.00"),
        offer_for_sale_cr=Decimal("200.00"),
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
    """Tests for IPO models, lifecycle domain logic, research analytics, and views."""

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

    def test_subscription_analytics_service(self, ipo_dataset):
        """Tests time-series subscription aggregation, delta calculation, and momentum classification."""
        live = ipo_dataset["live"]
        summary = get_subscription_summary(live)
        assert summary["has_data"] is True
        assert summary["latest"].total_subscription == Decimal("7.30")
        assert summary["snapshots_count"] == 2
        assert summary["is_oversubscribed"] is True

        # Delta calculation verification (Day 2 - Day 1: 7.30 - 1.10 = 6.20x)
        assert summary["history"][0]["delta"] == Decimal("1.10")
        assert summary["history"][1]["delta"] == Decimal("6.20")
        assert summary["momentum_label"] == "Steady Demand Growth"

        # Test IPO without snapshots
        upcoming = ipo_dataset["upcoming"]
        empty_summary = get_subscription_summary(upcoming)
        assert empty_summary["has_data"] is False
        assert empty_summary["momentum_label"] == "No Bids Recorded"

    def test_financial_research_metrics_computation(self, ipo_dataset):
        """Tests 3-year CAGR, margin derivation, debt-to-equity, and peer valuation benchmarking."""
        live = ipo_dataset["live"]
        fund = live.fundamentals
        metrics = compute_financial_metrics(fund, live)

        assert metrics["has_fundamentals"] is True
        # Revenue went from 100 to 225 over 2 periods: sqrt(225/100) - 1 = 1.5 - 1 = 50.0%
        assert metrics["cagr_3yr"] == Decimal("50.0")
        # EBITDA margin = 45 / 225 = 20.0%
        assert metrics["ebitda_margin"] == Decimal("20.0")
        # PAT margin = 25 / 225 = 11.11%
        assert metrics["pat_margin"] == Decimal("11.11")
        # Debt to equity = 90 / 300 = 0.30
        assert metrics["debt_to_equity"] == Decimal("0.30")
        # Fresh issue ratio = 350 / 500 = 70.0%
        assert metrics["fresh_issue_ratio"] == Decimal("70.0")
        assert metrics["ofs_ratio"] == Decimal("30.0")
        # Valuation: 24.0 vs peer 35.0 -> (24 - 35) / 35 = -31.4% (Attractive Valuation)
        assert "Attractive Valuation" in metrics["valuation_status"]
        assert metrics["pe_diff_percent"] == Decimal("-31.4")
        assert len(metrics["peers"]) == 1

    def test_ipo_document_and_fundamentals_models(self, ipo_dataset):
        """Tests model relations and representation strings for IPODocument and IPOFundamentals."""
        live = ipo_dataset["live"]
        doc = live.documents.first()
        assert "TESTLIVE" in str(doc)
        assert doc.get_doc_type_display() == "Red Herring Prospectus (RHP)"

        fund = live.fundamentals
        assert "TESTLIVE Fundamentals" in str(fund)

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

    def test_ipo_research_list_view_and_sorting(self, client: Client, ipo_dataset):
        """Tests the Fundamental Research & Valuation directory view and sorting."""
        url = reverse("ipo:research")

        # Full page shell
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Fundamental Research" in content
        assert "TESTLIVE" in content

        # HTMX partial
        htmx_resp = client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        assert "<!DOCTYPE html>" not in htmx_resp.content.decode("utf-8")

        # Sector filtering
        resp_sector = client.get(f"{url}?sector=Utilities")
        assert resp_sector.status_code == 200
        assert "TESTLIVE" in resp_sector.content.decode("utf-8")

        # Sorting by CAGR
        resp_cagr = client.get(f"{url}?sort=cagr_desc")
        assert resp_cagr.status_code == 200

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

    def test_ipo_detail_view_and_tab_navigation(self, client: Client, ipo_dataset):
        """Tests full detail view and all 4 research tabs (overview, subscription, fundamentals, documents)."""
        base_url = reverse("ipo:detail", kwargs={"symbol": "TESTLIVE"})

        # Tab: Overview (default)
        resp = client.get(base_url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Test Live Energies Limited" in content
        assert "₹100 - ₹110" in content
        assert "Issue Overview" in content

        # Tab: Subscription
        resp_sub = client.get(f"{base_url}?tab=subscription", HTTP_HX_REQUEST="true")
        assert resp_sub.status_code == 200
        sub_content = resp_sub.content.decode("utf-8")
        assert "Live Bidding" in sub_content
        assert "7.30x" in sub_content

        # Tab: Fundamentals
        resp_fund = client.get(f"{base_url}?tab=fundamentals", HTTP_HX_REQUEST="true")
        assert resp_fund.status_code == 200
        fund_content = resp_fund.content.decode("utf-8")
        assert "Audited Financial Performance" in fund_content
        assert "Peer Energy A" in fund_content

        # Tab: Documents Vault
        resp_docs = client.get(f"{base_url}?tab=documents", HTTP_HX_REQUEST="true")
        assert resp_docs.status_code == 200
        docs_content = resp_docs.content.decode("utf-8")
        assert "Official Regulatory Filings" in docs_content
        assert "Test Live Energies - Red Herring Prospectus" in docs_content

        # Tab: Scoring & Quantitative Evaluation (Phase C)
        resp_scoring = client.get(f"{base_url}?tab=scoring", HTTP_HX_REQUEST="true")
        assert resp_scoring.status_code == 200
        scoring_content = resp_scoring.content.decode("utf-8")
        assert "Institutional Quantitative Evaluation" in scoring_content
        assert "7-Pillar Quantitative Factor Analysis" in scoring_content
        assert "Factor Radar Comparison" in scoring_content
        assert "Company Frontier" in scoring_content

        # 404 on nonexistent symbol
        resp_404 = client.get(reverse("ipo:detail", kwargs={"symbol": "NONEXISTENT"}))
        assert resp_404.status_code == 404

    def test_quantitative_scoring_engine(self, ipo_dataset):
        """Tests the 7-pillar quantitative evaluation, weights, confidence, and horizon evaluations."""
        live = ipo_dataset["live"]
        eval_result = evaluate_ipo_scoring(live, save=True)

        assert eval_result["business_score"] >= Decimal("70.00")
        assert eval_result["financials_score"] >= Decimal("60.00")
        assert eval_result["valuation_score"] >= Decimal("80.00")  # discount to peer
        assert eval_result["growth_score"] >= Decimal("80.00")
        assert eval_result["overall_score"] >= Decimal("70.00")
        assert eval_result["confidence_level"] == "HIGH"
        assert eval_result["data_completeness_percent"] >= Decimal("80.0")
        assert eval_result["recommendation"] in ["STRONG_RESEARCH_CANDIDATE", "CONSIDER_APPLYING"]
        assert eval_result["listing_gain_potential"] in ["HIGH", "MODERATE", "LOW"]
        assert eval_result["short_term_potential"] in ["POSITIVE", "NEUTRAL", "CAUTION"]
        assert eval_result["long_term_potential"] in ["POSITIVE", "NEUTRAL", "CAUTION"]
        assert len(eval_result["strengths_list"]) > 0

    def test_insufficient_data_scoring_classification(self, db):
        """Verifies that an IPO with minimal disclosures correctly receives INSUFFICIENT_DATA."""
        today = timezone.now().date()
        sparse_ipo = IPOMaster.objects.create(
            symbol="SPARSEIPO",
            company_name="Sparse Disclosures Limited",
            isin="INE00SPARSE1",
            issue_type=IssueType.MAINBOARD,
            exchange="NSE",
            status=IPOStatus.UPCOMING,
            open_date=today + timedelta(days=10),
            close_date=today + timedelta(days=13),
        )
        eval_result = evaluate_ipo_scoring(sparse_ipo, save=True)
        assert eval_result["recommendation"] == "INSUFFICIENT_DATA"
        assert eval_result["confidence_level"] == "LOW"
        assert eval_result["data_completeness_percent"] < Decimal("40.0")

    def test_radar_chart_geometry_calculation(self, ipo_dataset):
        """Verifies SVG spider/radar chart geometry generation."""
        live = ipo_dataset["live"]
        evaluate_ipo_scoring(live, save=True)
        live.refresh_from_db()

        radar = get_radar_chart_geometry(live.scoring)
        assert len(radar["grid_polygons"]) == 4
        assert len(radar["axes"]) == 7
        assert "data_polygon" in radar
        assert len(radar["data_polygon"].split()) == 7

    def test_seed_ipo_data_command(self):
        """Verifies that seed_ipo_data runs idempotently and populates canonical records with fundamentals and scores."""
        call_command("seed_ipo_data")
        assert IPOMaster.objects.filter(symbol="SWIGGY").exists()
        assert IPOMaster.objects.filter(symbol="WAAREEENER").exists()
        assert IPOMaster.objects.filter(symbol="HYUNDAI").exists()
        assert IPOMaster.objects.filter(symbol="BAJAJHFL").exists()
        assert IPOMaster.objects.filter(symbol="NTPCGREEN").exists()
        assert IPOMaster.objects.filter(symbol="BOSSPACK").exists()

        # Check seeded fundamentals, documents, and scoring
        swiggy = IPOMaster.objects.get(symbol="SWIGGY")
        assert hasattr(swiggy, "fundamentals")
        assert swiggy.fundamentals.revenue_cagr_3yr == Decimal("40.41")
        assert swiggy.documents.count() >= 3
        assert hasattr(swiggy, "scoring")
        assert swiggy.scoring.recommendation == "APPLY_WITH_CAUTION"

        waaree = IPOMaster.objects.get(symbol="WAAREEENER")
        assert waaree.fundamentals.revenue_fy_latest == Decimal("11397.61")
        assert waaree.subscriptions.count() == 3
        assert waaree.scoring.recommendation == "STRONG_RESEARCH_CANDIDATE"
        assert waaree.scoring.listing_gain_potential == "HIGH"
