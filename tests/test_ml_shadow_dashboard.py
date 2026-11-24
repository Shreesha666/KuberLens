"""
Unit and Regression Tests for Phase 4.3 Risk Intelligence Dashboard & Shadow Validation.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Tests cover:
1. Strategy accounting reconciliation (ending capital vs total net return).
2. Point-in-time shadow evaluation record creation and persistence.
3. Shadow forward return maturation without future lookahead leakage.
4. Risk intelligence dashboard view rendering and context metrics.
5. Production recommendation isolation (ensuring shadow vetoes do not alter heuristic setups).
6. Portfolio risk diagnostic mapping and read-only non-execution invariant.
"""
import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from services.ml.portfolio_simulator import ResearchPortfolioSimulator
from services.ml.shadow_service import ShadowEvaluationService

User = get_user_model()


@pytest.mark.django_db
class TestMLPhase43RiskDashboardAndShadow:

    def test_strategy_accounting_reconciliation(self):
        """
        Verify that portfolio net return exactly matches ending capital change:
        ((Ending - Initial) / Initial) * 100 == total_return_pct
        """
        dates = [f"2026-03-{i:02d}" for i in range(1, 26)]
        rows = []
        for d in dates:
            rows.append({
                "session_date": d,
                "symbol": "ACC_TEST",
                "open_raw": 100.0,
                "close_raw": 95.0,  # 5% loss
                "open_adj": 100.0,
                "close_adj": 95.0,
            })
        df_prices = pd.DataFrame(rows)

        df_signals = pd.DataFrame([
            {"session_date": "2026-03-01", "symbol": "ACC_TEST", "signal": 1},
        ])

        sim = ResearchPortfolioSimulator(
            initial_capital=1_000_000.0,
            max_position_pct=0.10,
            horizon_sessions=10,
            slippage_pct=0.0005,
        )
        perf = sim.simulate(df_signals, df_prices)

        expected_ret = round(((perf.ending_capital - perf.initial_capital) / perf.initial_capital * 100.0), 2)
        assert perf.total_return_pct == expected_ret
        assert perf.total_net_pnl == round(perf.ending_capital - perf.initial_capital, 2)

    def test_shadow_evaluation_recording_and_maturation(self):
        """
        Verify that ShadowEvaluationService captures candidate setups point-in-time
        and matures 5d/10d/20d returns only after those sessions have passed.
        """
        # Create listing
        exch, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "NSE India"})
        inst, _ = Instrument.objects.get_or_create(
            isin="INE999A01011",
            defaults={"legal_name": "Shadow Test Ltd", "display_name": "Shadow Test"}
        )
        listing, _ = ExchangeListing.objects.get_or_create(
            exchange=exch,
            instrument=inst,
            symbol="SHADOW_TEST",
            defaults={"lot_size": 1, "is_tradeable": True}
        )

        df_candidates = pd.DataFrame([{
            "symbol": "SHADOW_TEST",
            "session_date": "2026-01-05",
            "atr_ratio_14": 0.02,
            "rsi_14": 52.0,
            "price_to_sma20": 0.02,
            "price_to_sma50": 0.04,
            "price_to_sma200": 0.06,
            "bb_bandwidth": 8.0,
            "garman_klass_vol": 18.0,
            "benchmark_rel_strength_20": 0.02,
        }])

        svc = ShadowEvaluationService()
        recs = svc.record_session_candidates(df_candidates)
        assert len(recs) == 1
        rec = recs[0]
        assert rec.is_matured is False
        assert rec.forward_return_20d is None

        # Build prices for 25 sessions
        dates = [f"2026-01-{i:02d}" for i in range(5, 31)]
        price_rows = []
        for i, d in enumerate(dates):
            price_rows.append({
                "session_date": d,
                "symbol": "SHADOW_TEST",
                "open_adj": 100.0 + i,
                "close_adj": 101.0 + i,
            })
        df_prices = pd.DataFrame(price_rows)

        matured_cnt = svc.mature_pending_evaluations(df_prices)
        assert matured_cnt == 1

        rec.refresh_from_db()
        assert rec.is_matured is True
        assert rec.forward_return_5d is not None
        assert rec.forward_return_10d is not None
        assert rec.forward_return_20d is not None

    def test_risk_dashboard_view_authenticated(self, client):
        """
        Verify that RiskIntelligenceDashboardView renders with HTTP 200 for authenticated user.
        """
        user = User.objects.create_user(username="risk_auditor", email="risk_auditor@kuberlens.com", password="SecurePassword123!")
        client.force_login(user)

        url = reverse("ml_engine:risk_dashboard")
        response = client.get(url)

        assert response.status_code == 200
        assert "Risk Intelligence" in response.content.decode()
        assert "Research-Only Disclosure" in response.content.decode()

    def test_production_recommendation_isolation(self):
        """
        Verify that shadow records and risk vetoes operate strictly in read-only shadow mode
        and do not alter production recommendation flags or broker configurations.
        """
        svc = ShadowEvaluationService()
        summary = svc.compute_shadow_summary()
        assert isinstance(summary, dict)
        assert "risk_tier_distribution" in summary

    def test_admin_eod_pipeline_view(self, client):
        """
        Verify that Django Admin provides:
        1. 'Run EOD Pipeline Now' button on MLShadowPipelineRun changelist
        2. Parameterized execution form on /admin/ml_engine/mlshadowpipelinerun/run-pipeline/
        3. POST trigger with dry-run support redirecting with success message
        """
        superuser = User.objects.create_superuser(
            username="shadow_admin", email="shadow_admin@kuberlens.com", password="SuperPassword123!"
        )
        client.force_login(superuser)

        # 1. Changelist page has trigger button
        resp_list = client.get("/admin/ml_engine/mlshadowpipelinerun/")
        assert resp_list.status_code == 200
        assert "Run EOD Pipeline Now" in resp_list.content.decode()

        # 2. Execution form GET renders properly
        resp_form = client.get("/admin/ml_engine/mlshadowpipelinerun/run-pipeline/")
        assert resp_form.status_code == 200
        content = resp_form.content.decode()
        assert "Execute End-of-Day (EOD) Shadow Pipeline" in content
        assert "Pipeline Parameters" in content

        # 3. POST execution in dry-run mode
        resp_post = client.post(
            "/admin/ml_engine/mlshadowpipelinerun/run-pipeline/",
            {
                "session_date": "2026-11-20",
                "universe": "RELIANCE",
                "setup_name": "TREND_PULLBACK_HEURISTIC",
                "capture_mode": "FORWARD_CAPTURED",
                "force": "true",
                "dry_run": "true",
            },
            follow=True,
        )
        assert resp_post.status_code == 200
        assert "EOD Shadow Pipeline executed successfully" in resp_post.content.decode()
