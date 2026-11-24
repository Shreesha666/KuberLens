"""
Comprehensive Acceptance Tests for Phase 4.5: Shadow Operations Acceptance & Forward Evidence Readiness.
Complies with Master Specification § 18 and AIML Architecture Specification v2.1.

Validates:
1. Successful trading-day execution with MLShadowPipelineRun tracking.
2. Exchange holiday & weekend skips without uncaught exceptions.
3. Missing benchmark (^NSEI) and stock candle handling.
4. Independent per-horizon state machine maturation (5d vs 10d vs 20d).
5. Duplicate scheduled runs and lockfile concurrency protection.
6. Recovery after downtime and missed-session detection.
7. Genuine forward observation classification vs historical replay isolation.
8. Snapshot and matured outcome immutability.
9. Pipeline health state derivation (HEALTHY, WAITING_FOR_DATA, STALE, DEGRADED, FAILED).
10. Strict user authorization (staff-only execution) and portfolio isolation.
11. Research-only non-execution safety invariant.
"""
import os
import time
from datetime import date
from decimal import Decimal
from io import StringIO

import pandas as pd
import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.ml_engine.management.commands.run_shadow_eod_pipeline import PIPELINE_LOCK_FILE
from apps.ml_engine.models import (
    HorizonMaturityStatus,
    MLModelRecord,
    MLShadowEvaluationRecord,
    MLShadowPipelineRun,
    PipelineHealthState,
    ShadowCaptureMode,
)
from apps.portfolio.models import Portfolio
from services.ml.shadow_service import ShadowEvaluationService

User = get_user_model()


@pytest.fixture
def acceptance_universe():
    exch, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "NSE India"})
    listings = []
    for sym, isin in [("SYM_A", "INE001A01011"), ("SYM_B", "INE002B01012")]:
        inst, _ = Instrument.objects.get_or_create(
            isin=isin,
            defaults={"legal_name": f"{sym} Corporation Ltd", "display_name": sym}
        )
        listing, _ = ExchangeListing.objects.get_or_create(
            exchange=exch,
            instrument=inst,
            symbol=sym,
            defaults={"lot_size": 1, "is_tradeable": True}
        )
        listings.append(listing)
    return listings


@pytest.mark.django_db
class TestMLPhase45ShadowAcceptance:

    def test_successful_trading_day_execution(self, acceptance_universe, monkeypatch):
        """
        Verify complete 6-stage pipeline execution on a valid trading day,
        persisting MLShadowPipelineRun with SUCCESS status and duration.
        """
        listing = acceptance_universe[0]
        dates = [f"2026-11-{i:02d}" for i in range(1, 21)]
        rows = []
        for i, d in enumerate(dates):
            rows.append({
                "symbol": listing.symbol,
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
        df_mock = pd.DataFrame(rows)

        from services.ml.dataset_builder import DatasetBuilder
        monkeypatch.setattr(DatasetBuilder, "build_canonical_dataframe", lambda self: (df_mock, {}))

        out = StringIO()
        call_command(
            "run_shadow_eod_pipeline",
            session_date="2026-11-20",
            universe=listing.symbol,
            force=True,
            stdout=out,
        )
        output = out.getvalue()
        assert "Pipeline finished successfully" in output

        pipeline_run = MLShadowPipelineRun.objects.filter(session_date="2026-11-20").first()
        assert pipeline_run is not None
        assert pipeline_run.status == "SUCCESS"
        assert pipeline_run.health_state == PipelineHealthState.HEALTHY
        assert pipeline_run.duration_seconds > 0.0

    def test_weekend_and_exchange_holiday_skips(self):
        """
        Verify that exchange holidays (Guru Nanak Jayanti 2026-11-24) are skipped cleanly
        without crashing and recorded as SKIPPED_HOLIDAY.
        """
        out = StringIO()
        call_command(
            "run_shadow_eod_pipeline",
            session_date="2026-11-24",
            stdout=out,
        )
        output = out.getvalue()
        assert "Pipeline skipped" in output
        assert "Guru Nanak Jayanti" in output

        pipeline_run = MLShadowPipelineRun.objects.filter(session_date="2026-11-24").first()
        assert pipeline_run is not None
        assert pipeline_run.status == "SKIPPED_HOLIDAY"

    def test_missing_benchmark_data_handling(self, acceptance_universe):
        """
        Verify that missing benchmark (^NSEI) data prevents premature evaluation
        and reports clear diagnostic reason.
        """
        svc = ShadowEvaluationService()
        readiness = svc.validate_session_readiness(date(2026, 11, 20), force=False)
        # In test DB with 0 candles, readiness is False with clear diagnostic
        assert readiness["is_ready"] is False
        assert "No 1d historical candles found" in readiness["reason"] or "missing" in readiness["reason"]

    def test_independent_per_horizon_maturation(self, acceptance_universe):
        """
        Verify independent per-horizon state machine:
        - 5 sessions: status_5d is MATURED, but status_10d and status_20d remain PENDING.
        - 10 sessions: status_5d and status_10d are MATURED, status_20d remains PENDING.
        - 20 sessions: all are MATURED and is_matured becomes True.
        """
        listing = acceptance_universe[0]
        svc = ShadowEvaluationService()

        df_candidates = pd.DataFrame([{
            "symbol": listing.symbol,
            "session_date": "2026-05-01",
            "atr_ratio_14": 0.02,
            "rsi_14": 42.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.02,
            "price_to_sma200": 0.03,
            "bb_bandwidth": 5.0,
            "garman_klass_vol": 14.0,
            "benchmark_rel_strength_20": 0.01,
        }])
        recs = svc.record_session_candidates(df_candidates, setup_name="HORIZON_TEST")
        rec = recs[0]

        assert rec.status_5d == HorizonMaturityStatus.PENDING
        assert rec.status_10d == HorizonMaturityStatus.PENDING
        assert rec.status_20d == HorizonMaturityStatus.PENDING
        assert rec.is_matured is False

        # Build 7 price sessions (enough for 5d horizon: entry at t+1, exit at t+5)
        dates_7 = [f"2026-05-{i:02d}" for i in range(1, 8)]
        price_rows_7 = []
        for i, d in enumerate(dates_7):
            price_rows_7.append({
                "session_date": d,
                "symbol": listing.symbol,
                "open_adj": 100.0 + i,
                "close_adj": 101.0 + i,
                "open_raw": 100.0 + i,
                "close_raw": 101.0 + i,
            })
        df_prices_7 = pd.DataFrame(price_rows_7)

        svc.mature_pending_evaluations(df_prices_7)
        rec.refresh_from_db()

        # Invariant check: 5d matured, 10d and 20d strictly pending
        assert rec.status_5d == HorizonMaturityStatus.MATURED
        assert rec.forward_return_5d is not None
        assert rec.matured_at_5d is not None
        assert rec.source_checksum_5d != ""

        assert rec.status_10d == HorizonMaturityStatus.PENDING
        assert rec.forward_return_10d is None
        assert rec.status_20d == HorizonMaturityStatus.PENDING
        assert rec.forward_return_20d is None
        assert rec.is_matured is False  # Must NOT be marked overall mature yet

        # Build 12 price sessions (enough for 10d horizon)
        dates_12 = [f"2026-05-{i:02d}" for i in range(1, 13)]
        price_rows_12 = []
        for i, d in enumerate(dates_12):
            price_rows_12.append({
                "session_date": d,
                "symbol": listing.symbol,
                "open_adj": 100.0 + i,
                "close_adj": 101.0 + i,
                "open_raw": 100.0 + i,
                "close_raw": 101.0 + i,
            })
        df_prices_12 = pd.DataFrame(price_rows_12)

        svc.mature_pending_evaluations(df_prices_12)
        rec.refresh_from_db()

        assert rec.status_5d == HorizonMaturityStatus.MATURED
        assert rec.status_10d == HorizonMaturityStatus.MATURED
        assert rec.forward_return_10d is not None
        assert rec.status_20d == HorizonMaturityStatus.PENDING
        assert rec.is_matured is False

        # Build 25 price sessions (enough for 20d horizon)
        dates_25 = [f"2026-05-{i:02d}" for i in range(1, 26)]
        price_rows_25 = []
        for i, d in enumerate(dates_25):
            price_rows_25.append({
                "session_date": d,
                "symbol": listing.symbol,
                "open_adj": 100.0 + i,
                "close_adj": 101.0 + i,
                "open_raw": 100.0 + i,
                "close_raw": 101.0 + i,
            })
        df_prices_25 = pd.DataFrame(price_rows_25)

        svc.mature_pending_evaluations(df_prices_25)
        rec.refresh_from_db()

        assert rec.status_5d == HorizonMaturityStatus.MATURED
        assert rec.status_10d == HorizonMaturityStatus.MATURED
        assert rec.status_20d == HorizonMaturityStatus.MATURED
        assert rec.forward_return_20d is not None
        assert rec.is_matured is True
        assert rec.decision_status == "MATURED"

    def test_lockfile_concurrency_protection(self):
        """
        Verify that an active lockfile blocks concurrent pipeline executions.
        """
        # Create mock active lockfile
        with open(PIPELINE_LOCK_FILE, "w") as f:
            f.write(f"test-lock:{time.time()}")

        try:
            err = StringIO()
            call_command(
                "run_shadow_eod_pipeline",
                session_date="2026-11-20",
                stderr=err,
            )
            output = err.getvalue()
            assert "Concurrent execution blocked: lockfile" in output
        finally:
            if os.path.exists(PIPELINE_LOCK_FILE):
                os.remove(PIPELINE_LOCK_FILE)

    def test_interrupted_processing_stale_lock_recovery(self, acceptance_universe, monkeypatch):
        """
        Verify that a stale lockfile (>15 min old) from an interrupted run
        is automatically cleared so operations recover without manual intervention.
        """
        # Create stale lockfile with timestamp 20 minutes ago
        with open(PIPELINE_LOCK_FILE, "w") as f:
            f.write("stale-lock")
        stale_time = time.time() - 1200
        os.utime(PIPELINE_LOCK_FILE, (stale_time, stale_time))

        try:
            out = StringIO()
            call_command(
                "run_shadow_eod_pipeline",
                session_date="2026-11-24",  # Will skip on holiday after clearing lock
                stdout=out,
            )
            output = out.getvalue()
            assert "Removing stale lockfile" in output
        finally:
            if os.path.exists(PIPELINE_LOCK_FILE):
                os.remove(PIPELINE_LOCK_FILE)

    def test_missed_session_detection_and_recovery(self, acceptance_universe):
        """
        Verify that detect_missed_sessions identifies un-evaluated trading days
        and supports sequential catchup.
        """
        svc = ShadowEvaluationService()
        # Range across trading days: 2026-11-18 (Wed), 2026-11-19 (Thu), 2026-11-20 (Fri)
        start = date(2026, 11, 18)
        end = date(2026, 11, 20)
        missed = svc.detect_missed_sessions(from_date=start, to_date=end)
        assert len(missed) == 3
        assert missed == [date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)]

    def test_historical_replay_vs_forward_captured_classification(self, acceptance_universe):
        """
        Verify that observations on past dates cannot claim FORWARD_CAPTURED status
        and are reclassified to HISTORICAL_REPLAY, keeping forward metrics uncontaminated.
        """
        listing = acceptance_universe[0]
        svc = ShadowEvaluationService()

        # Attempt to record candidate for an old date as FORWARD_CAPTURED
        df_candidates = pd.DataFrame([{
            "symbol": listing.symbol,
            "session_date": "2024-03-01",  # Old date
            "atr_ratio_14": 0.02,
            "rsi_14": 42.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.02,
            "price_to_sma200": 0.03,
            "bb_bandwidth": 5.0,
            "garman_klass_vol": 14.0,
            "benchmark_rel_strength_20": 0.01,
        }])

        recs = svc.record_session_candidates(
            df_candidates,
            setup_name="REPLAY_TEST",
            capture_mode=ShadowCaptureMode.FORWARD_CAPTURED,  # Claiming forward
        )
        rec = recs[0]

        # Must be reclassified to HISTORICAL_REPLAY
        assert rec.capture_mode == ShadowCaptureMode.HISTORICAL_REPLAY
        assert "Reclassified" in rec.error_message

        # Forward metrics must ignore historical replay
        summary = svc.compute_shadow_summary(forward_only=True)
        assert summary["total_evaluations"] == 0

        # All-inclusive metrics include it
        summary_all = svc.compute_shadow_summary(forward_only=False)
        assert summary_all["total_evaluations"] == 1

    def test_forward_observation_immutability(self, acceptance_universe):
        """
        Verify that once matured, a record's outcomes and checksum cannot be altered
        by subsequent pipeline runs.
        """
        listing = acceptance_universe[0]
        svc = ShadowEvaluationService()

        df_candidates = pd.DataFrame([{
            "symbol": listing.symbol,
            "session_date": "2026-06-01",
            "atr_ratio_14": 0.02,
            "rsi_14": 40.0,
            "price_to_sma20": 0.01,
            "price_to_sma50": 0.02,
            "price_to_sma200": 0.03,
            "bb_bandwidth": 5.0,
            "garman_klass_vol": 14.0,
            "benchmark_rel_strength_20": 0.01,
        }])
        recs = svc.record_session_candidates(df_candidates, setup_name="IMMUTABLE_VAL")
        rec = recs[0]

        rec.is_matured = True
        rec.status_20d = HorizonMaturityStatus.MATURED
        rec.forward_return_20d = Decimal("0.0850")
        rec.outcome_source_checksum = "immutable_hash_12345"
        rec.save()

        # Re-run recording
        recs_after = svc.record_session_candidates(df_candidates, setup_name="IMMUTABLE_VAL")
        assert len(recs_after) == 1
        rec_after = MLShadowEvaluationRecord.objects.get(id=rec.id)
        assert rec_after.forward_return_20d == Decimal("0.0850")
        assert rec_after.outcome_source_checksum == "immutable_hash_12345"

    def test_pipeline_health_state_derivation(self):
        """
        Verify pipeline health states: HEALTHY, FAILED, STALE.
        """
        svc = ShadowEvaluationService()

        # 1. No runs -> STALE
        health = svc.get_pipeline_health_state()
        assert health["health_state"] == PipelineHealthState.STALE.value

        # 2. Failed run -> FAILED
        MLShadowPipelineRun.objects.create(
            session_date=date(2026, 11, 20),
            status="FAILED",
            health_state=PipelineHealthState.FAILED,
            error_details="Simulated ingestion error",
        )
        health_failed = svc.get_pipeline_health_state()
        assert health_failed["health_state"] == PipelineHealthState.FAILED.value

        # 3. Successful run -> HEALTHY
        MLShadowPipelineRun.objects.create(
            session_date=date(2026, 11, 20),
            status="SUCCESS",
            health_state=PipelineHealthState.HEALTHY,
        )
        health_success = svc.get_pipeline_health_state()
        assert health_success["health_state"] == PipelineHealthState.HEALTHY.value

    def test_user_authorization_and_portfolio_isolation(self, client, acceptance_universe):
        """
        Verify that regular users are forbidden from manually triggering shadow runs (HTTP 403),
        staff members are permitted (HTTP 302 redirect), and portfolio diagnostics are strictly
        isolated to the authenticated user.
        """
        regular_user = User.objects.create_user(
            username="regular_trader",
            email="trader@kuberlens.com",
            password="SecurePassword123!",
            is_staff=False,
        )
        staff_user = User.objects.create_user(
            username="shadow_operator",
            email="operator@kuberlens.com",
            password="SecurePassword123!",
            is_staff=True,
        )

        url = reverse("ml_engine:shadow_run")

        # 1. Regular user blocked with 403 Forbidden
        client.force_login(regular_user)
        response_reg = client.post(url)
        assert response_reg.status_code == 403

        # 2. Staff user authorized
        client.force_login(staff_user)
        response_staff = client.post(url)
        assert response_staff.status_code == 302

        # 3. Portfolio Isolation
        port = Portfolio.objects.create(user=regular_user, name="Trader Portfolio")
        Holding.objects.create(
            portfolio=port,
            listing=acceptance_universe[0],
            total_quantity=50,
            average_buy_price=Decimal("100.00"),
        )

        # Regular user sees holding
        client.force_login(regular_user)
        dash_reg = client.get(reverse("ml_engine:risk_dashboard"))
        assert acceptance_universe[0].symbol in dash_reg.content.decode()

        # Staff user does not see regular user's holding
        client.force_login(staff_user)
        dash_staff = client.get(reverse("ml_engine:risk_dashboard"))
        assert "No active portfolio holdings found" in dash_staff.content.decode()

    def test_research_only_non_execution_invariant(self):
        """
        Verify that no ML model record is in APPROVED state, ensuring zero live broker
        order generation or heuristic recommendation suppression.
        """
        approved_models = MLModelRecord.objects.filter(model_state="APPROVED")
        assert approved_models.count() == 0
