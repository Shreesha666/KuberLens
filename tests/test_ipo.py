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

from apps.holdings.models import Holding, HoldingTransaction, TransactionType
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.ipo.models import (
    DocumentType,
    IPOApplication,
    IPODocument,
    IPOFundamentals,
    IPOMaster,
    IPOStatus,
    IPOSubscriptionSnapshot,
    IssueType,
)
from apps.portfolio.models import Portfolio
from services.ipo.comparison import compare_ipos
from services.ipo.lifecycle import get_status_badge_class, get_timeline_milestones
from services.ipo.performance import (
    compute_ipo_performance_metrics,
)
from services.ipo.planner import calculate_bid_plan, estimate_allotment_probability
from services.ipo.predictor import predict_listing_gain_and_recommendation
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
        # In a live issue, DRHP/RHP is completed by statutory necessity
        assert milestones[0]["status"] == "COMPLETED"
        assert milestones[0]["display_date"] != "TBA"

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

    def test_ipo_issues_list_pagination(self, client: Client, db):
        """Tests that IPOIssuesListView paginates results at 15 items per page and preserves query parameters."""
        today = timezone.now().date()
        # Create 20 test IPO records
        for i in range(20):
            IPOMaster.objects.create(
                symbol=f"PAGEIPO{i:02d}",
                company_name=f"Page Test Company {i:02d} Ltd",
                status=IPOStatus.UPCOMING,
                issue_type=IssueType.MAINBOARD,
                exchange="NSE",
                open_date=today + timedelta(days=i + 1),
                close_date=today + timedelta(days=i + 4),
            )

        url = reverse("ipo:issues")

        # Page 1 request with filter params
        resp_p1 = client.get(f"{url}?tab=upcoming&type=MAINBOARD&sort=name_asc&page=1")
        assert resp_p1.status_code == 200
        content_p1 = resp_p1.content.decode("utf-8")
        assert resp_p1.context["page_obj"].paginator.num_pages >= 2
        assert len(resp_p1.context["ipos"]) == 15
        assert "Showing" in content_p1
        assert "Page 1 of" in content_p1
        # Check that page 2 link exists and preserves query params
        assert "page=2" in content_p1
        assert "tab=upcoming" in content_p1
        assert "type=MAINBOARD" in content_p1
        assert "sort=name_asc" in content_p1

        # Page 2 request
        resp_p2 = client.get(f"{url}?tab=upcoming&type=MAINBOARD&sort=name_asc&page=2")
        assert resp_p2.status_code == 200
        assert resp_p2.context["page_obj"].number == 2
        assert len(resp_p2.context["ipos"]) == 5
        content_p2 = resp_p2.content.decode("utf-8")
        assert "page=1" in content_p2
        assert "Page 2 of" in content_p2

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

        # Tab: Interactive Bid Planner (Phase D)
        resp_planner = client.get(f"{base_url}?tab=planner", HTTP_HX_REQUEST="true")
        assert resp_planner.status_code == 200
        planner_content = resp_planner.content.decode("utf-8")
        assert "Bid Parameters" in planner_content
        assert "Total Funds to be Blocked" in planner_content
        assert "SEBI Retail Lottery Allotment Probability" in planner_content

        # 404 on nonexistent symbol
        resp_404 = client.get(reverse("ipo:detail", kwargs={"symbol": "NONEXISTENT"}))
        assert resp_404.status_code == 404

    def test_bid_planner_calculations_and_limits(self, ipo_dataset):
        """Tests lot sizing, UPI payment limits, category statutory boundaries, and scenarios."""
        live = ipo_dataset["live"]

        # 1 Lot Retail (₹11,000 <= 2 Lakhs, eligible, UPI)
        plan_retail = calculate_bid_plan(live, category="RETAIL", lots=1, is_cutoff=True)
        assert plan_retail["total_shares"] == 100
        assert plan_retail["total_amount"] == Decimal("11000.00")
        assert plan_retail["is_eligible"] is True
        assert plan_retail["payment_mode"] == "UPI_MANDATE"
        assert len(plan_retail["warnings"]) == 0
        assert len(plan_retail["scenarios"]) == 5

        # 20 Lots Retail (₹2,20,000 > 2 Lakhs, ineligible)
        plan_retail_excess = calculate_bid_plan(live, category="RETAIL", lots=20, is_cutoff=True)
        assert plan_retail_excess["is_eligible"] is False
        assert any("exceeds the SEBI ₹2,00,000 statutory limit" in w for w in plan_retail_excess["warnings"])

        # sHNI Category with 1 Lot (₹11,000 <= 2L, ineligible)
        plan_shni_low = calculate_bid_plan(live, category="sHNI", lots=1, is_cutoff=False)
        assert plan_shni_low["is_eligible"] is False
        assert any("strictly exceed ₹2,00,000" in w for w in plan_shni_low["warnings"])

        # sHNI Category with 25 Lots (₹2,75,000 > 2L and <= 10L, eligible)
        plan_shni_ok = calculate_bid_plan(live, category="sHNI", lots=25, is_cutoff=False)
        assert plan_shni_ok["is_eligible"] is True
        assert plan_shni_ok["payment_mode"] == "UPI_MANDATE"  # <= 5L

        # Big HNI with 60 Lots (₹6,60,000 > 5L, ASBA NetBanking)
        plan_asba = calculate_bid_plan(live, category="sHNI", lots=60, is_cutoff=False)
        assert plan_asba["payment_mode"] == "ASBA_NETBANKING"

    def test_allotment_probability_estimator(self, ipo_dataset):
        """Tests mathematical SEBI retail lottery probability and multi-PAN family diversification odds."""
        live = ipo_dataset["live"]

        # Retail oversubscribed at 7.30x (Day 2 snapshot)
        est = estimate_allotment_probability(live, category="RETAIL", lots_applied=1, num_pan_accounts=1)
        assert est["is_lottery"] is True
        assert est["single_pan_probability"] < Decimal("20.0")  # ~13.7%
        assert len(est["family_scenarios"]) == 5
        assert any("SEBI Lottery Rule" in note for note in est["compliance_notes"])

        # Multi-PAN family odds increase: P(3 accounts) > P(1 account)
        est_family = estimate_allotment_probability(live, category="RETAIL", lots_applied=1, num_pan_accounts=3)
        assert est_family["selected_probability"] > est["single_pan_probability"]

        # Undersubscribed IPO: upcoming has no bids -> 100% allotment
        upcoming = ipo_dataset["upcoming"]
        est_upcoming = estimate_allotment_probability(upcoming, category="RETAIL", lots_applied=1)
        assert est_upcoming["is_lottery"] is False
        assert est_upcoming["single_pan_probability"] == Decimal("100.0")
        assert est_upcoming["is_awaiting_data"] is True

    def test_sebi_lot_sizing_and_lottery_edge_cases(self, ipo_dataset):
        """Tests SEBI statutory lot size properties and subscription fallback logic."""
        from apps.ipo.models import IssueType, IPOSubscriptionSnapshot

        # 1. Mainboard statutory lot sizing when lot_size is unpopulated (1)
        mb_ipo = IPOMaster.objects.create(
            symbol="TESTMB_LOT",
            company_name="Test Mainboard Ltd",
            issue_type=IssueType.MAINBOARD,
            status=IPOStatus.LIVE,
            price_band_min=Decimal("95.00"),
            price_band_max=Decimal("100.00"),
            lot_size=1,
        )
        assert mb_ipo.effective_lot_size == 148
        assert mb_ipo.calculated_min_investment == Decimal("14800.00")

        # 2. SME statutory lot sizing when lot_size is unpopulated (1)
        sme_ipo = IPOMaster.objects.create(
            symbol="TESTSME_LOT",
            company_name="Test SME Ltd",
            issue_type=IssueType.SME,
            status=IPOStatus.LIVE,
            price_band_min=Decimal("95.00"),
            price_band_max=Decimal("100.00"),
            lot_size=1,
        )
        assert sme_ipo.effective_lot_size >= 1000
        assert sme_ipo.calculated_min_investment >= Decimal("100000.00")

        # 3. Subscription fallback: retail_subscription is 0.00, total_subscription is 25.00x
        IPOSubscriptionSnapshot.objects.create(
            ipo=mb_ipo,
            day_number=1,
            qib_subscription=Decimal("0.00"),
            nii_subscription=Decimal("0.00"),
            retail_subscription=Decimal("0.00"),
            total_subscription=Decimal("25.00"),
        )
        est_fallback = estimate_allotment_probability(mb_ipo, category="RETAIL", lots_applied=1, num_pan_accounts=1)
        assert est_fallback["is_lottery"] is True
        assert est_fallback["subscription_multiple"] == Decimal("25.00")
        assert est_fallback["single_pan_probability"] == Decimal("4.00")

        # 4. Family multi-PAN odds enhancement: P(3 accounts) = 1 - (1 - 0.04)^3 = 11.5%
        est_fam3 = estimate_allotment_probability(mb_ipo, category="RETAIL", lots_applied=1, num_pan_accounts=3)
        assert est_fam3["selected_probability"] == 11.5

    def test_listing_gain_predictor_and_recommendation_engine(self, ipo_dataset):
        """Tests empirical listing gain prediction, price bands, and recommendation signals."""
        from apps.ipo.models import IPOGMPRecord

        live = ipo_dataset["live"]
        # Add a mock GMP record of ₹35 on ₹110 upper band (+31.8%)
        IPOGMPRecord.objects.create(
            ipo=live,
            reported_gmp=Decimal("35.00"),
            estimated_listing_price=Decimal("145.00"),
            estimated_gain_percent=Decimal("31.80"),
        )

        pred = predict_listing_gain_and_recommendation(live)
        assert pred["has_prediction"] is True
        assert pred["predicted_price_min"] > Decimal("110.00")
        assert pred["predicted_price_max"] > pred["predicted_price_min"]
        assert pred["expected_gain_midpoint"] > Decimal("20.00")
        assert pred["recommendation"] in ["STRONG_APPLY", "APPLY_RETAIL_LOTTERY"]
        assert "Book Listing Gains" in pred["listing_day_strategy"] or "Family PAN" in pred["listing_day_strategy"]
        assert len(pred["rationale"]) > 0

        # Test pre-issue DRHP without price band
        drhp_ipo = IPOMaster.objects.create(
            symbol="TESTDRHP",
            company_name="Test DRHP Limited",
            status=IPOStatus.DRHP_FILED,
            price_band_min=None,
            price_band_max=None,
        )
        pred_drhp = predict_listing_gain_and_recommendation(drhp_ipo)
        assert pred_drhp["has_prediction"] is False
        assert pred_drhp["recommendation"] == "AWAIT_PRICING"

    def test_bid_planner_views_and_htmx(self, client: Client, ipo_dataset):
        """Tests the standalone Bid Planner view and HTMX live parameter updates."""
        live = ipo_dataset["live"]
        url = reverse("ipo:bid_planner", kwargs={"symbol": live.symbol})

        # Full page shell
        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode("utf-8")
        assert "Interactive Bid Planner" in content
        assert "Number of Lots" in content
        assert "Total Funds to be Blocked" in content

        # HTMX partial swap with custom parameters
        htmx_url = f"{url}?category=RETAIL&lots=3&cutoff=true&pans=2"
        htmx_resp = client.get(htmx_url, HTTP_HX_REQUEST="true")
        assert htmx_resp.status_code == 200
        htmx_content = htmx_resp.content.decode("utf-8")
        assert "<!DOCTYPE html>" not in htmx_content
        assert "₹33,000.00" in htmx_content  # 3 lots * 100 shares * ₹110
        assert "300 shares" in htmx_content

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

    def test_ipo_application_list_view_and_filtering(self, client: Client, ipo_dataset, django_user_model):
        """Verifies personal IPO application ledger view, status tabs, and KPI aggregation."""
        user = django_user_model.objects.create_user(username="investor1", password="password123")
        client.login(username="investor1", password="password123")

        live = ipo_dataset["live"]
        sme = ipo_dataset["sme"]

        # 1. Awaiting application
        IPOApplication.objects.create(
            user=user,
            ipo=live,
            application_number="APP-101",
            lots_applied=2,
            shares_applied=200,
            bid_price=Decimal("110.00"),
            applied_amount=Decimal("22000.00"),
            mandate_status="APPROVED",
            allotment_status="AWAITING",
        )

        # 2. Allotted application
        IPOApplication.objects.create(
            user=user,
            ipo=sme,
            application_number="APP-102",
            lots_applied=1,
            shares_applied=100,
            bid_price=Decimal("120.00"),
            applied_amount=Decimal("12000.00"),
            mandate_status="APPROVED",
            allotment_status="ALLOTTED",
            allotted_shares=100,
            allotted_amount=Decimal("12000.00"),
        )

        # Full page request
        url = reverse("ipo:applications")
        res = client.get(url)
        assert res.status_code == 200
        assert res.context["total_applications_count"] == 2
        assert res.context["total_blocked_funds"] == Decimal("22000.00")
        assert res.context["total_allotted_funds"] == Decimal("12000.00")
        assert "APP-101" in res.content.decode()
        assert "APP-102" in res.content.decode()

        # HTMX partial request with filter
        htmx_res = client.get(url + "?status=AWAITING", HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        content = htmx_res.content.decode()
        assert "APP-101" in content
        assert "APP-102" not in content

    def test_ipo_log_application_view(self, client: Client, ipo_dataset, django_user_model):
        """Verifies logging a new bid application from Bid Planner or standalone tracker."""
        user = django_user_model.objects.create_user(username="investor2", password="password123")
        client.login(username="investor2", password="password123")
        live = ipo_dataset["live"]

        post_url = reverse("ipo:application_create")
        payload = {
            "ipo_id": live.id,
            "investor_category": "RETAIL",
            "lots_applied": 3,
            "bid_price": "110.00",
            "is_cutoff_bid": "true",
            "application_number": "APP-TEST-999",
            "demat_account": "Zerodha (12345678)",
            "listing_strategy": "BOOK_PROFIT",
            "mandate_status": "APPROVED",
            "notes": "Testing bid logging",
        }
        res = client.post(post_url, data=payload)
        assert res.status_code == 302

        app = IPOApplication.objects.get(application_number="APP-TEST-999")
        assert app.user == user
        assert app.ipo == live
        assert app.lots_applied == 3
        assert app.shares_applied == 300  # 3 lots * 100
        assert app.applied_amount == Decimal("33000.00")
        assert app.demat_account == "Zerodha (12345678)"
        assert app.listing_strategy == "BOOK_PROFIT"

    def test_ipo_update_application_outcome_view(self, client: Client, ipo_dataset, django_user_model):
        """Verifies updating allotment status, allotted shares and calculating refund amount."""
        user = django_user_model.objects.create_user(username="investor3", password="password123")
        client.login(username="investor3", password="password123")
        live = ipo_dataset["live"]

        app = IPOApplication.objects.create(
            user=user,
            ipo=live,
            application_number="APP-OUTCOME-1",
            lots_applied=2,
            shares_applied=200,
            bid_price=Decimal("100.00"),
            applied_amount=Decimal("20000.00"),
            allotment_status="AWAITING",
        )

        outcome_url = reverse("ipo:application_outcome", kwargs={"pk": app.pk})
        res = client.post(outcome_url, data={
            "allotment_status": "PARTIALLY_ALLOTTED",
            "allotted_shares": 100,
            "mandate_status": "APPROVED",
            "notes": "Partial lot allotment received",
        })
        assert res.status_code == 302

        app.refresh_from_db()
        assert app.allotment_status == "PARTIALLY_ALLOTTED"
        assert app.allotted_shares == 100
        assert app.allotted_amount == Decimal("10000.00")
        assert app.refund_amount == Decimal("10000.00")

    def test_ipo_transfer_to_portfolio_view(self, client: Client, ipo_dataset, django_user_model):
        """Verifies 1-click sync from Allotted IPO to Portfolio Holdings via FIFOAccountingEngine."""
        user = django_user_model.objects.create_user(username="investor4", password="password123")
        client.login(username="investor4", password="password123")
        live = ipo_dataset["live"]

        # Create Instrument & ExchangeListing for live IPO
        exchange, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "NSE"})
        instrument = Instrument.objects.create(
            isin=live.isin,
            legal_name=live.company_name,
            display_name=live.company_name,
        )
        listing = ExchangeListing.objects.create(
            instrument=instrument,
            exchange=exchange,
            symbol=live.symbol,
            is_tradeable=True,
        )
        live.listing = listing
        live.save()

        # Create allotted IPO application
        app = IPOApplication.objects.create(
            user=user,
            ipo=live,
            application_number="APP-TRANSFER-1",
            lots_applied=1,
            shares_applied=100,
            bid_price=Decimal("110.00"),
            applied_amount=Decimal("11000.00"),
            allotment_status="ALLOTTED",
            allotted_shares=100,
            allotted_amount=Decimal("11000.00"),
            transferred_to_portfolio=False,
        )

        transfer_url = reverse("ipo:application_transfer_portfolio", kwargs={"pk": app.pk})
        res = client.post(transfer_url)
        assert res.status_code == 302

        app.refresh_from_db()
        assert app.transferred_to_portfolio is True

        # Verify HoldingTransaction and Holding exist
        portfolio = Portfolio.objects.get(user=user, is_default=True)
        tx = HoldingTransaction.objects.filter(portfolio=portfolio, listing=listing).first()
        assert tx is not None
        assert tx.transaction_type == TransactionType.BUY
        assert tx.quantity == 100
        assert tx.price == Decimal("110.00")

        holding = Holding.objects.filter(portfolio=portfolio, listing=listing).first()
        assert holding is not None
        assert holding.total_quantity == 100
        assert holding.invested_amount == Decimal("11000.00")

    def test_ipo_application_delete_view(self, client: Client, ipo_dataset, django_user_model):
        """Verifies deletion of an application record."""
        user = django_user_model.objects.create_user(username="investor5", password="password123")
        client.login(username="investor5", password="password123")
        live = ipo_dataset["live"]

        app = IPOApplication.objects.create(
            user=user,
            ipo=live,
            application_number="APP-DEL-1",
            lots_applied=1,
            shares_applied=100,
            bid_price=Decimal("100.00"),
            applied_amount=Decimal("10000.00"),
        )

        del_url = reverse("ipo:application_delete", kwargs={"pk": app.pk})
        res = client.post(del_url)
        assert res.status_code == 302
        assert not IPOApplication.objects.filter(pk=app.pk).exists()

    def test_ipo_performance_computation_and_horizons(self, ipo_dataset):
        """Verifies calculation of listing day gains, drift, current returns, and benchmark alpha."""
        sme = ipo_dataset["sme"]
        metrics = compute_ipo_performance_metrics(sme)

        assert metrics["issue_price"] == Decimal("75.00")
        assert metrics["listing_day_close"] == Decimal("125.00")
        assert metrics["listing_gain_percent"] == Decimal("66.67")
        assert metrics["current_price"] == Decimal("125.00")
        assert metrics["total_return_percent"] == Decimal("66.67")
        assert metrics["performance_category"] == "SUPER_OUTPERFORMER"
        assert metrics["benchmark_alpha"] > Decimal("0.00")

    def test_ipo_performance_view_and_filtering(self, client: Client, ipo_dataset):
        """Verifies post-listing performance desk view, type filtering and HTMX partial response."""
        url = reverse("ipo:performance")
        res = client.get(url)
        assert res.status_code == 200
        assert "summary" in res.context
        assert res.context["summary"]["total_listed_count"] >= 1
        assert "TESTSME" in res.content.decode()

        # HTMX partial with SME filter
        htmx_res = client.get(url + "?type=SME", HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        content = htmx_res.content.decode()
        assert "TESTSME" in content

    def test_ipo_comparison_service_and_narrative(self, ipo_dataset):
        """Verifies multi-IPO side-by-side comparison matrix and automated narrative generation."""
        live = ipo_dataset["live"]
        sme = ipo_dataset["sme"]

        comparison = compare_ipos([live.symbol, sme.symbol])
        assert "error" not in comparison
        assert len(comparison["ipos"]) == 2
        assert len(comparison["headers"]) == 2
        assert len(comparison["rows"]) >= 10
        assert comparison["leader"] is not None
        assert len(comparison["narrative"]) > 0

    def test_ipo_comparison_view_and_presets(self, client: Client, ipo_dataset):
        """Verifies multi-IPO comparison view, URL query params, and HTMX partial rendering."""
        live = ipo_dataset["live"]
        sme = ipo_dataset["sme"]

        url = reverse("ipo:compare") + f"?symbols={live.symbol},{sme.symbol}"
        res = client.get(url)
        assert res.status_code == 200
        assert "comparison" in res.context
        assert len(res.context["comparison"]["ipos"]) == 2
        assert live.symbol in res.content.decode()
        assert sme.symbol in res.content.decode()

        # HTMX partial
        htmx_res = client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        assert "Side-by-Side Metric Matrix" in htmx_res.content.decode()

    def test_ipo_detail_performance_tab(self, client: Client, ipo_dataset):
        """Verifies ?tab=performance on IPODetailView renders listing day metrics and horizon returns."""
        sme = ipo_dataset["sme"]
        url = reverse("ipo:detail", kwargs={"symbol": sme.symbol}) + "?tab=performance"
        res = client.get(url)
        assert res.status_code == 200
        assert res.context["active_tab"] == "performance"
        assert "performance_metrics" in res.context
        assert res.context["performance_metrics"]["listing_gain_percent"] == Decimal("66.67")
        assert "Listing Day vs Current Market Return" in res.content.decode()

    def test_ipos_markets_sync_service_and_view(self, client: Client, db, monkeypatch):
        """Verifies ipos.markets sync logic, data model upsert, and IPOSyncView HTMX response."""
        from services.ipo.ipos_markets_client import IPOSMarketsClient
        from services.ipo.sync import sync_ipos_markets

        mock_overview = {
            "counts": {"total": 1, "mainboard": 1, "sme": 0},
            "open": [
                {
                    "slug": "mock-solar-energy-limited",
                    "name": "Mock Solar Energy Limited",
                    "board": "mainboard",
                    "stage": "open",
                    "symbol": "MOCKSOLAR",
                    "open": "2026-11-10",
                    "close": "2026-11-14",
                    "listing": "2026-11-20",
                    "band": "100-110",
                    "price": 110.0,
                    "size": 500.0,
                    "sub": 4.5,
                }
            ],
            "upcoming": [],
            "recent": [],
        }

        mock_detail = {
            "slug": "mock-solar-energy-limited",
            "display": "Mock Solar Energy Limited",
            "isin": "INE00MOCK123",
            "symbols": {"nse": "MOCKSOLAR"},
            "board": "mainboard",
            "stage": "open",
            "open_date": "2026-11-10",
            "close_date": "2026-11-14",
            "listing_date": "2026-11-20",
            "issue_price": 110.0,
            "price_band": {"min": 100.0, "max": 110.0},
            "lot_size": 100,
            "issue_size_cr": 500.0,
            "fresh_issue_cr": 350.0,
            "ofs_cr": 150.0,
            "subscription": {
                "latest": {
                    "total_times": 4.5,
                    "categories": {
                        "Qualified Institutional Buyers(QIBs)": {"times": 6.2},
                        "Non Institutional Investors": {"times": 3.8},
                        "Retail Individual Investors(RIIs)": {"times": 2.1},
                    },
                }
            },
        }

        fake_client = IPOSMarketsClient()
        monkeypatch.setattr(fake_client, "get_overview", lambda: mock_overview)
        monkeypatch.setattr(fake_client, "get_issue_detail", lambda slug: mock_detail)

        stats = sync_ipos_markets(client=fake_client, live_only=False, detail_limit=5)
        assert stats["created"] == 1
        assert stats["errors"] == 0

        synced_ipo = IPOMaster.objects.get(symbol="MOCKSOLAR")
        assert synced_ipo.company_name == "Mock Solar Energy Limited"
        assert synced_ipo.price_band_min == Decimal("100.00")
        assert synced_ipo.price_band_max == Decimal("110.00")
        assert synced_ipo.lot_size == 100

        # Check subscription snapshot was seeded
        sub = IPOSubscriptionSnapshot.objects.get(ipo=synced_ipo)
        assert sub.total_subscription == Decimal("4.50")
        assert sub.qib_subscription == Decimal("6.20")

        # Test IPOSyncView with HTMX
        sync_url = reverse("ipo:sync")
        with monkeypatch.context() as m:
            m.setattr("services.ipo.sync.sync_ipos_markets", lambda **kwargs: {"created": 0, "updated": 1, "errors": 0})
            htmx_res = client.post(sync_url, HTTP_HX_REQUEST="true")
            assert htmx_res.status_code == 200
            assert "IPO Intelligence Centre" in htmx_res.content.decode()

    def test_registrar_adapters_and_dispatcher(self):
        """Tests multi-registrar allotment enquiry adapters and dispatcher resolution."""
        from services.ipo.registrars import (
            BigshareAdapter,
            KFintechAdapter,
            LinkIntimeAdapter,
            get_registrar_adapter,
        )

        assert isinstance(get_registrar_adapter("Link Intime India Private Ltd"), LinkIntimeAdapter)
        assert isinstance(get_registrar_adapter("KFin Technologies Limited"), KFintechAdapter)
        assert isinstance(get_registrar_adapter("Bigshare Services Pvt Ltd"), BigshareAdapter)

        link_adapter = LinkIntimeAdapter()
        res = link_adapter.query_allotment(
            ipo_symbol="SWIGGY",
            company_name="Swiggy Limited",
            pan="ABCDE1234F",
        )
        assert res["success"] is True
        assert res["status"] in ["AWAITING", "ALLOTTED", "NOT_ALLOTTED"]
        assert "Link Intime" in res["registrar_name"]

    def test_ipo_strategy_backtester(self, ipo_dataset):
        """Tests the IPO quantitative strategy backtester across historical listed IPOs."""
        from services.ipo.backtester import run_ipo_backtest

        # Test unrestricted universe
        res_all = run_ipo_backtest(initial_capital=Decimal("100000.00"))
        assert res_all["total_in_universe"] >= 1
        assert res_all["total_matched"] >= 1
        assert res_all["win_rate"] >= Decimal("0.00")
        assert len(res_all["equity_curve"]) >= 2

        # Test with strict high QIB filter
        res_qib = run_ipo_backtest(min_qib_sub=Decimal("100.00"))
        # Should have 0 matches with an impossible 100x QIB filter on the fixture
        assert res_qib["total_matched"] == 0

    def test_family_vault_and_batch_apply(self, client: Client, ipo_dataset):
        """Tests Family Member Demat Vault creation and 1-click batch application in Bid Planner."""
        from django.contrib.auth import get_user_model
        from apps.ipo.models import IPOFamilyMember

        User = get_user_model()
        user = User.objects.create_user(username="vault_user", password="password123")
        client.force_login(user)

        # 1. Add Family Member via POST
        create_url = reverse("ipo:family_member_create")
        res = client.post(create_url, {
            "name": "Priya Sharma",
            "pan": "ABCDE1234F",
            "relationship": "SPOUSE",
            "demat_account": "1208160012345678",
            "default_upi_id": "priya@okaxis",
            "asba_bank_name": "HDFC Bank",
            "is_primary": "true",
        })
        assert res.status_code == 302
        member = IPOFamilyMember.objects.get(user=user, pan="ABCDE1234F")
        assert member.masked_pan == "ABCDE****F"
        assert member.is_primary is True

        # 2. View Family Vault
        vault_url = reverse("ipo:family_vault")
        v_res = client.get(vault_url)
        assert v_res.status_code == 200
        assert "Priya Sharma" in v_res.content.decode()

        # 3. 1-Click Batch Apply in Bid Planner
        live = ipo_dataset["live"]
        batch_url = reverse("ipo:batch_apply", kwargs={"symbol": live.symbol})
        b_res = client.post(batch_url, {
            "family_members": [str(member.id)],
            "lots": 1,
            "category": "RETAIL",
        })
        assert b_res.status_code == 302

        # Check IPOApplication was created and linked to family member
        app = IPOApplication.objects.get(user=user, ipo=live, family_member=member)
        assert app.lots_applied == 1
        assert app.allotment_status == "AWAITING"
        assert app.demat_account == member.demat_account

    def test_registrar_check_view_and_application_flow(self, client: Client, ipo_dataset):
        """Tests direct registrar check action on an active application."""
        from django.contrib.auth import get_user_model
        from apps.ipo.models import IPOFamilyMember

        User = get_user_model()
        user = User.objects.create_user(username="reg_user", password="password123")
        client.force_login(user)

        live = ipo_dataset["live"]
        member = IPOFamilyMember.objects.create(
            user=user,
            name="Ramesh",
            pan="KLMNO5678P",
            demat_account="1208160098765432",
        )
        app = IPOApplication.objects.create(
            user=user,
            ipo=live,
            family_member=member,
            investor_category="RETAIL",
            lots_applied=1,
            shares_applied=100,
            bid_price=Decimal("110.00"),
            applied_amount=Decimal("11000.00"),
            allotment_status="AWAITING",
        )

        reg_check_url = reverse("ipo:application_registrar_check", kwargs={"pk": app.pk})
        res = client.post(reg_check_url)
        assert res.status_code == 302
        app.refresh_from_db()
        assert app.allotment_status in ["AWAITING", "ALLOTTED", "NOT_ALLOTTED"]




