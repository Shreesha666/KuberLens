"""
Unit and Integration Tests for Phase 4.4: Automated Shadow Monitoring, Data Integrity & Operational Hardening.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Tests cover:
1. Deterministic SHA-256 cryptographic feature and outcome checksum calculation.
2. Exchange calendar session readiness verification (trading days, holidays, market close).
3. Idempotent shadow decision recording under transactional concurrency.
4. Preserving matured records against unintentional overwrite.
5. Accurate forward maturation with Indian statutory friction (STT, GST, SEBI, Stamp Duty) via IndianTaxCalculator.
6. End-to-End EOD management command execution (dry-run, holiday skip, and active run).
7. Operational monitoring event logging (MLMonitoringEvent) and pipeline dashboard context telemetry.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.ml_engine.models import (
    MLMonitoringEvent,
    MLShadowEvaluationRecord,
    MLShadowPipelineRun,
)
from services.ml.shadow_service import (
    ShadowEvaluationService,
    compute_feature_checksum,
    compute_outcome_checksum,
)

User = get_user_model()


@pytest.fixture
def test_listing():
    exch, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "NSE India"})
    inst, _ = Instrument.objects.get_or_create(
        isin="INE999P04401",
        defaults={"legal_name": "Pipeline Test Equities Ltd", "display_name": "Pipeline Test"}
    )
    listing, _ = ExchangeListing.objects.get_or_create(
        exchange=exch,
        instrument=inst,
        symbol="PIPE_TEST",
        defaults={"lot_size": 1, "is_tradeable": True}
    )
    return listing


@pytest.mark.django_db
class TestMLPhase44ShadowPipeline:

    def test_feature_and_outcome_checksum_determinism(self):
        """
        Verify that compute_feature_checksum and compute_outcome_checksum are deterministic,
        reproducible regardless of key order, and sensitive to value perturbations.
        """
        dict_a = {"rsi_14": 42.5, "price_to_sma200": 0.05, "atr_ratio": 0.02}
        dict_b = {"atr_ratio": 0.02, "rsi_14": 42.5, "price_to_sma200": 0.05}
        dict_perturbed = {"rsi_14": 42.50001, "price_to_sma200": 0.05, "atr_ratio": 0.02}

        hash_a = compute_feature_checksum(dict_a)
        hash_b = compute_feature_checksum(dict_b)
        hash_pert = compute_feature_checksum(dict_perturbed)

        assert len(hash_a) == 64
        assert hash_a == hash_b  # Key order invariance
        assert hash_a != hash_pert  # Perturbation sensitivity

        # Outcome checksum
        outcome_a = {"entry_open_adj": 100.0, "exit_20d_close_adj": 105.0}
        outcome_b = {"exit_20d_close_adj": 105.0, "entry_open_adj": 100.0}
        assert compute_outcome_checksum(outcome_a) == compute_outcome_checksum(outcome_b)

    def test_session_calendar_readiness_validation(self):
        """
        Verify that validate_session_readiness correctly identifies exchange holidays,
        trading days, and missing benchmark/market data.
        """
        svc = ShadowEvaluationService()

        # 1. Holiday: Guru Nanak Jayanti on 2026-11-24
        res_holiday = svc.validate_session_readiness(date(2026, 11, 24), force=False)
        assert res_holiday["is_ready"] is False
        assert res_holiday["is_trading_day"] is False
        assert "Guru Nanak Jayanti" in str(res_holiday["holiday_reason"])

        # 2. Forced holiday validation
        res_holiday_forced = svc.validate_session_readiness(date(2026, 11, 24), force=True)
        # Even if force=True, if no candles exist it still reports readiness accordingly
        assert res_holiday_forced["is_trading_day"] is False

        # 3. Known trading session: 2026-11-20
        res_trading = svc.validate_session_readiness(date(2026, 11, 20), force=True)
        assert res_trading["is_trading_day"] is True

    def test_record_session_candidates_idempotency_and_checksum(self, test_listing):
        """
        Verify that record_session_candidates persists records with SHA-256 checksums,
        respects unique constraints, and prevents duplicate record creation.
        """
        svc = ShadowEvaluationService()
        df_candidates = pd.DataFrame([{
            "symbol": test_listing.symbol,
            "session_date": "2026-06-15",
            "atr_ratio_14": 0.02,
            "rsi_14": 42.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.03,
            "price_to_sma200": 0.05,
            "bb_bandwidth": 6.5,
            "garman_klass_vol": 15.0,
            "benchmark_rel_strength_20": 0.01,
        }])

        # First recording
        recs1 = svc.record_session_candidates(df_candidates, setup_name="TEST_SETUP")
        assert len(recs1) == 1
        rec1 = recs1[0]
        assert rec1.feature_snapshot_checksum != ""
        assert len(rec1.feature_snapshot_checksum) == 64
        assert rec1.decision_status == "PENDING_MATURATION"
        assert rec1.source_provider == "AUTHENTIC_EOD"

        # Second recording for same session should update, not duplicate
        recs2 = svc.record_session_candidates(df_candidates, setup_name="TEST_SETUP")
        assert len(recs2) == 1
        assert MLShadowEvaluationRecord.objects.filter(listing=test_listing, session_date="2026-06-15").count() == 1

    def test_matured_record_immutability(self, test_listing):
        """
        Verify that once a shadow record is matured, subsequent candidate recording
        calls do not overwrite the matured outcome.
        """
        svc = ShadowEvaluationService()
        df_candidates = pd.DataFrame([{
            "symbol": test_listing.symbol,
            "session_date": "2026-07-01",
            "atr_ratio_14": 0.02,
            "rsi_14": 45.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.02,
            "price_to_sma200": 0.04,
            "bb_bandwidth": 5.0,
            "garman_klass_vol": 14.0,
            "benchmark_rel_strength_20": 0.01,
        }])
        recs = svc.record_session_candidates(df_candidates, setup_name="IMMUTABLE_TEST")
        rec = recs[0]

        # Simulate maturation
        rec.is_matured = True
        rec.decision_status = "MATURED"
        rec.forward_return_20d = Decimal("0.0520")
        rec.outcome_source_checksum = "test_outcome_hash"
        rec.save()

        # Re-recording candidates should not overwrite the matured record
        recs_after = svc.record_session_candidates(df_candidates, setup_name="IMMUTABLE_TEST")
        assert len(recs_after) == 1
        rec_check = MLShadowEvaluationRecord.objects.get(id=rec.id)
        assert rec_check.is_matured is True
        assert rec_check.forward_return_20d == Decimal("0.0520")
        assert rec_check.outcome_source_checksum == "test_outcome_hash"

    def test_forward_maturation_with_indian_market_frictions(self, test_listing):
        """
        Verify that mature_pending_evaluations calculates realistic net returns
        accounting for next-session open (O_{t+1}) entry fill and IndianTaxCalculator friction.
        """
        svc = ShadowEvaluationService()
        df_candidates = pd.DataFrame([{
            "symbol": test_listing.symbol,
            "session_date": "2026-08-01",
            "atr_ratio_14": 0.02,
            "rsi_14": 44.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.02,
            "price_to_sma200": 0.04,
            "bb_bandwidth": 6.0,
            "garman_klass_vol": 16.0,
            "benchmark_rel_strength_20": 0.02,
        }])
        svc.record_session_candidates(df_candidates, setup_name="FRICTION_TEST")

        # Build 25 price sessions
        dates = [f"2026-08-{i:02d}" for i in range(1, 28)]
        price_rows = []
        for i, d in enumerate(dates):
            # Session 0: 2026-08-01 (Signal)
            # Session 1: 2026-08-02 (Entry Open: 100.0)
            # Session 5: 2026-08-06 (Exit 5d Close: 102.0) -> Gross +2.0%
            # Session 10: 2026-08-11 (Exit 10d Close: 104.0) -> Gross +4.0%
            # Session 20: 2026-08-21 (Exit 20d Close: 108.0) -> Gross +8.0%
            price_rows.append({
                "session_date": d,
                "symbol": test_listing.symbol,
                "open_adj": 100.0 + (i * 0.4),
                "close_adj": 100.0 + (i * 0.4),
                "open_raw": 100.0 + (i * 0.4),
                "close_raw": 100.0 + (i * 0.4),
            })
        df_prices = pd.DataFrame(price_rows)

        matured_count = svc.mature_pending_evaluations(df_prices, use_tax_calculator=True)
        assert matured_count == 1

        rec = MLShadowEvaluationRecord.objects.get(listing=test_listing, session_date="2026-08-01", setup_name="FRICTION_TEST")
        assert rec.is_matured is True
        assert rec.decision_status == "MATURED"
        assert rec.outcome_matured_at is not None
        assert rec.outcome_source_checksum != ""
        assert len(rec.outcome_source_checksum) == 64

        # Net return should be gross return minus Indian equity friction (~0.35%)
        # For 20d: entry open is session 1 (100.4), exit close is session 20 (108.0)
        # Gross = (108.0 - 100.4) / 100.4 = 7.57%
        # Net should be strictly less than gross due to statutory deductions
        gross_20d = (108.0 - 100.4) / 100.4
        assert float(rec.forward_return_20d) < gross_20d
        assert float(rec.forward_return_20d) > 0.05  # Still positive

    def test_run_shadow_eod_pipeline_holiday_skip(self):
        """
        Verify that running the management command on an exchange holiday
        gracefully skips execution and logs an MLMonitoringEvent.
        """
        out = StringIO()
        call_command(
            "run_shadow_eod_pipeline",
            session_date="2026-11-24",
            stdout=out,
        )
        output = out.getvalue()
        assert "Pipeline skipped: Date 2026-11-24 is not an exchange trading day" in output
        assert "Guru Nanak Jayanti" in output

        # Check monitoring event
        event = MLMonitoringEvent.objects.filter(event_type="SHADOW_PIPELINE_SKIPPED").first()
        assert event is not None
        assert event.details["session_date"] == "2026-11-24"

    def test_run_shadow_eod_pipeline_active_execution(self, test_listing, monkeypatch):
        """
        Verify that running the management command executes all stages,
        processes canonical price data, and logs a success MLMonitoringEvent.
        """
        # Build mock canonical DataFrame
        dates = [f"2026-11-{i:02d}" for i in range(1, 21)]
        rows = []
        for i, d in enumerate(dates):
            rows.append({
                "symbol": test_listing.symbol,
                "session_date": d,
                "open_raw": 100.0 + i,
                "high_raw": 102.0 + i,
                "low_raw": 99.0 + i,
                "close_raw": 101.0 + i,
                "volume_raw": 500_000,
                "open_adj": 100.0 + i,
                "high_adj": 102.0 + i,
                "low_adj": 99.0 + i,
                "close_adj": 101.0 + i,
                "volume_adj": 500_000.0,
                "benchmark_close_raw": 24000.0 + i,
                "benchmark_close_adj": 24000.0 + i,
            })
        df_canonical_mock = pd.DataFrame(rows)

        # Monkeypatch DatasetBuilder.build_canonical_dataframe
        from services.ml.dataset_builder import DatasetBuilder
        monkeypatch.setattr(DatasetBuilder, "build_canonical_dataframe", lambda self: (df_canonical_mock, {}))

        out = StringIO()
        call_command(
            "run_shadow_eod_pipeline",
            session_date="2026-11-20",
            universe=test_listing.symbol,
            force=True,
            stdout=out,
        )
        output = out.getvalue()
        assert "=== KuberLens AI/ML: EOD Shadow Evaluation Pipeline ===" in output
        assert "[Stage 1/6]" in output
        assert "[Stage 2/6]" in output
        assert "[Stage 3/6]" in output
        assert "[Stage 4/6]" in output
        assert "[Stage 5/6]" in output
        assert "[Stage 6/6]" in output
        assert "Pipeline finished successfully" in output

        # Check monitoring event
        event = MLMonitoringEvent.objects.filter(event_type="SHADOW_PIPELINE_RUN").order_by("-created_at").first()
        assert event is not None
        assert event.details["status"] == "SUCCESS"
        assert event.details["session_date"] == "2026-11-20"

    def test_risk_dashboard_view_pipeline_telemetry(self, client):
        """
        Verify that RiskIntelligenceDashboardView exposes pipeline_status,
        recent_monitoring_events, and data freshness to the template context.
        """
        user = User.objects.create_user(username="pipeline_auditor", email="auditor@kuberlens.com", password="SecurePassword123!")
        client.force_login(user)

        # Log a dummy pipeline run and event to verify display
        MLShadowPipelineRun.objects.create(
            session_date=date(2026, 11, 20),
            status="SUCCESS",
            health_state="HEALTHY",
        )
        svc = ShadowEvaluationService()
        svc.record_pipeline_event(
            event_type="SHADOW_PIPELINE_RUN",
            severity="LOW",
            details={"session_date": "2026-11-20", "status": "SUCCESS", "candidates_count": 0},
        )

        url = reverse("ml_engine:risk_dashboard")
        response = client.get(url)

        assert response.status_code == 200
        content = response.content.decode()
        assert "Pipeline: HEALTHY" in content
        assert "EOD Freshness:" in content
        assert "AUTHENTIC_EOD" in content
        assert "feat-v2.1.0" in content
        assert "Pipeline Operational Health &amp; Monitoring Log" in content
        assert "SHADOW_PIPELINE_RUN" in content
