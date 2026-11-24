"""
Unit and integration tests for Phase 4.6: Deployment Verification & Forward Research Monitoring.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Verifies:
1. Operational scheduler timezone correctness (19:15 IST == 13:45 UTC).
2. Service definition files (launchd plist, systemd timer, cron runner script).
3. DatabasePipelineLeaseManager atomic acquisition, mutual exclusion, heartbeats, and crash recovery.
4. Evidence-based forward capture validation (causality, post-market window, clock skew, force replay).
5. Immutability of genuine FORWARD_CAPTURED records.
6. Pipeline health telemetry and RiskIntelligenceDashboardView rendering.
"""
from __future__ import annotations

import os
import plistlib
from datetime import date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import (
    MLPipelineLease,
    MLShadowEvaluationRecord,
    ShadowCaptureMode,
)
from services.ml.shadow_service import (
    DatabasePipelineLeaseManager,
    ShadowEvaluationService,
    validate_forward_capture_evidence,
)


@pytest.fixture
def auth_client(db):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="audit_operator",
        email="operator@kuberlens.internal",
        password="TestPassword123!",
        is_staff=True,
    )
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def sample_listing(db):
    exchange, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "National Stock Exchange of India"})
    inst = Instrument.objects.create(
        isin="INE009A01021",
        legal_name="Infosys Limited",
        display_name="INFY",
    )
    listing = ExchangeListing.objects.create(
        instrument=inst,
        exchange=exchange,
        symbol="INFY",
        is_tradeable=True,
    )
    return listing


# ==============================================================================
# 1. Scheduler Timezone & Service Definition Tests
# ==============================================================================


def test_scheduler_timezone_ist_to_utc_conversion():
    """
    Validates that target 19:15 IST exactly corresponds to 13:45 UTC.
    Market closes at 15:30 IST; Bhavcopy settles ~18:30-19:00 IST.
    """
    ist = ZoneInfo("Asia/Kolkata")
    utc = ZoneInfo("UTC")

    test_date = date(2026, 4, 15)
    eod_ist = datetime.combine(test_date, dtime(19, 15), tzinfo=ist)
    eod_utc = eod_ist.astimezone(utc)

    assert eod_utc.hour == 13
    assert eod_utc.minute == 45
    assert (eod_ist - eod_utc.astimezone(ist)).total_seconds() == 0.0


def test_launchd_plist_configuration():
    """
    Validates that scripts/com.kuberlens.shadow.eod.plist exists and is configured
    for Monday-Friday at 19:15 IST with valid paths and arguments.
    """
    plist_path = "scripts/com.kuberlens.shadow.eod.plist"
    assert os.path.exists(plist_path), f"Missing launchd plist file: {plist_path}"

    with open(plist_path, "rb") as f:
        plist_data = plistlib.load(f)

    assert plist_data["Label"] == "com.kuberlens.shadow.eod"
    assert "scripts/run_shadow_eod_cron.sh" in plist_data["ProgramArguments"][1]

    intervals = plist_data.get("StartCalendarInterval", [])
    assert len(intervals) == 5, "Expected 5 weekday schedule entries (Mon-Fri)"

    weekdays_seen = set()
    for entry in intervals:
        assert entry["Hour"] == 19
        assert entry["Minute"] == 15
        weekdays_seen.add(entry["Weekday"])

    # launchd Weekday: 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri
    assert weekdays_seen == {1, 2, 3, 4, 5}


def test_systemd_timer_configuration():
    """
    Validates that scripts/kuberlens-shadow-eod.timer exists and triggers Mon..Fri at 13:45:00 UTC.
    """
    timer_path = "scripts/kuberlens-shadow-eod.timer"
    assert os.path.exists(timer_path), f"Missing systemd timer file: {timer_path}"

    with open(timer_path) as f:
        content = f.read()

    assert "OnCalendar=Mon..Fri 13:45:00 UTC" in content
    assert "Persistent=true" in content


# ==============================================================================
# 2. Database Pipeline Lease Manager Tests
# ==============================================================================


@pytest.mark.django_db
def test_lease_acquisition_and_mutual_exclusion():
    """
    Validates atomic lease acquisition, mutual exclusion between workers,
    and same-owner re-entrant renewal.
    """
    lease_name = "TEST_SHADOW_LEASE"
    owner_a = "worker_alpha"
    owner_b = "worker_beta"

    # 1. Worker A acquires unallocated lease
    acquired_a = DatabasePipelineLeaseManager.acquire_lease(
        lease_name=lease_name,
        owner_id=owner_a,
        lease_duration_seconds=300,
    )
    assert acquired_a is True
    assert DatabasePipelineLeaseManager.is_lease_active(lease_name) is True

    # 2. Worker B attempts to acquire same active lease -> Mutual Exclusion Blocked
    acquired_b = DatabasePipelineLeaseManager.acquire_lease(
        lease_name=lease_name,
        owner_id=owner_b,
        lease_duration_seconds=300,
    )
    assert acquired_b is False

    # 3. Worker A re-acquires / renews own lease -> Allowed
    renew_a = DatabasePipelineLeaseManager.acquire_lease(
        lease_name=lease_name,
        owner_id=owner_a,
        lease_duration_seconds=600,
    )
    assert renew_a is True

    # 4. Worker A releases lease
    released = DatabasePipelineLeaseManager.release_lease(lease_name, owner_a)
    assert released is True
    assert DatabasePipelineLeaseManager.is_lease_active(lease_name) is False

    # 5. Worker B now successfully acquires formerly released lease
    acquired_b_after = DatabasePipelineLeaseManager.acquire_lease(
        lease_name=lease_name,
        owner_id=owner_b,
        lease_duration_seconds=300,
    )
    assert acquired_b_after is True
    DatabasePipelineLeaseManager.release_lease(lease_name, owner_b)


@pytest.mark.django_db
def test_lease_heartbeat_renewal():
    """
    Validates that renew_heartbeat updates heartbeat_at and extends expires_at.
    """
    lease_name = "TEST_HEARTBEAT_LEASE"
    owner = "heartbeat_worker"

    DatabasePipelineLeaseManager.acquire_lease(lease_name, owner, lease_duration_seconds=100)
    info_before = DatabasePipelineLeaseManager.get_lease_info(lease_name)
    assert info_before is not None

    # Renew heartbeat
    renewed = DatabasePipelineLeaseManager.renew_heartbeat(lease_name, owner, extension_seconds=500)
    assert renewed is True

    info_after = DatabasePipelineLeaseManager.get_lease_info(lease_name)
    assert info_after["expires_at"] > info_before["expires_at"]

    # Heartbeat by unauthorized owner fails
    fail_renew = DatabasePipelineLeaseManager.renew_heartbeat(lease_name, "imposter", extension_seconds=500)
    assert fail_renew is False

    DatabasePipelineLeaseManager.release_lease(lease_name, owner)


@pytest.mark.django_db
def test_lease_crash_recovery_expired_takeover():
    """
    Validates crash recovery: if an unreleased lease expires in the past,
    a subsequent worker reclaims and takes over ownership safely.
    """
    lease_name = "TEST_CRASH_LEASE"
    crashed_worker = "crashed_worker_pid_101"
    new_worker = "healthy_worker_pid_102"

    # Manually create an expired active lease mimicking a hard SIGKILL crash
    past_time = timezone.now() - timedelta(minutes=15)
    MLPipelineLease.objects.create(
        lease_name=lease_name,
        owner_id=crashed_worker,
        acquired_at=past_time,
        heartbeat_at=past_time,
        expires_at=past_time + timedelta(seconds=60),  # expired 14 mins ago
        is_active=True,
    )

    info = DatabasePipelineLeaseManager.get_lease_info(lease_name)
    assert info["is_expired"] is True

    # New worker takes over expired lease
    acquired = DatabasePipelineLeaseManager.acquire_lease(lease_name, new_worker, lease_duration_seconds=600)
    assert acquired is True

    info_reclaimed = DatabasePipelineLeaseManager.get_lease_info(lease_name)
    assert info_reclaimed["owner_id"] == new_worker
    assert info_reclaimed["is_active"] is True
    assert info_reclaimed["is_expired"] is False

    DatabasePipelineLeaseManager.release_lease(lease_name, new_worker)


@pytest.mark.django_db(transaction=True)
def test_sqlite_concurrent_lease_contention():
    """
    Validates that under concurrent worker contention on SQLite, exactly one worker
    acquires the lease and no unhandled database locks or IntegrityErrors occur.
    """
    import concurrent.futures

    from django.db import connection

    lease_name = "TEST_CONCURRENT_THREAD_LEASE"

    def attempt_acquisition(worker_id):
        connection.close()  # Independent connection
        return DatabasePipelineLeaseManager.acquire_lease(
            lease_name=lease_name,
            owner_id=f"worker_{worker_id}",
            lease_duration_seconds=30,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_acquisition, i) for i in range(5)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    acquired_count = sum(1 for success in results if success)
    assert acquired_count == 1, f"Expected exactly 1 acquisition, got {acquired_count}"


# ==============================================================================
# 3. Evidence-Based Forward Capture Validation Tests
# ==============================================================================


def test_validate_forward_capture_valid_window():
    """
    Session on a trading day captured between 15:30 IST and 09:15 IST next session
    is classified as genuine FORWARD_CAPTURED.
    """
    ist = ZoneInfo("Asia/Kolkata")
    # Wednesday 2026-04-15
    session_date = date(2026, 4, 15)
    # Captured at 19:15 IST same day
    capture_time = datetime(2026, 4, 15, 19, 15, tzinfo=ist)
    data_as_of = datetime(2026, 4, 15, 18, 45, tzinfo=ist)

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=data_as_of,
        force=False,
        requested_mode=ShadowCaptureMode.FORWARD_CAPTURED,
    )

    assert mode == ShadowCaptureMode.FORWARD_CAPTURED
    assert "Valid post-market forward capture window" in reason


def test_validate_forward_capture_missing_source_ingestion_timestamp():
    """
    Observations without an authentic source-ingestion timestamp are reclassified
    to HISTORICAL_REPLAY.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)
    capture_time = datetime(2026, 4, 15, 19, 15, tzinfo=ist)

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=None,  # Missing authentic timestamp
        force=False,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "Missing authentic source-ingestion timestamp" in reason


def test_validate_forward_capture_pre_close_source_data():
    """
    Source data ingested prior to session close (15:30 IST) indicates incomplete
    daytime data and is reclassified to HISTORICAL_REPLAY even if capture occurred post-market.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)
    capture_time = datetime(2026, 4, 15, 19, 15, tzinfo=ist)
    data_as_of = datetime(2026, 4, 15, 14, 0, tzinfo=ist)  # Ingested during live market

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=data_as_of,
        force=False,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "Pre-close source data" in reason


def test_validate_forward_capture_reclassified_pre_close():
    """
    Session captured before 15:30 IST is reclassified to HISTORICAL_REPLAY.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)
    # Captured at 14:00 IST (pre-close)
    capture_time = datetime(2026, 4, 15, 14, 0, tzinfo=ist)
    data_as_of = datetime(2026, 4, 15, 13, 50, tzinfo=ist)

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=data_as_of,
        force=False,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "Pre-close capture" in reason


def test_validate_forward_capture_reclassified_retrospective_post_next_open():
    """
    Capture after next session opens (>= 09:15 IST next trading day) is reclassified
    to HISTORICAL_REPLAY because future execution prices are observable.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)  # Wednesday
    # Next session is Thursday 2026-04-16, opens at 09:15 IST
    # Capture time is Thursday 10:30 IST
    capture_time = datetime(2026, 4, 16, 10, 30, tzinfo=ist)

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=datetime(2026, 4, 15, 19, 0, tzinfo=ist),
        force=False,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "Retrospective capture" in reason


def test_validate_forward_capture_causality_clock_skew():
    """
    Causality violation (data timestamp is in the future relative to capture time)
    is reclassified to HISTORICAL_REPLAY.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)
    capture_time = datetime(2026, 4, 15, 19, 15, tzinfo=ist)
    future_data_time = datetime(2026, 4, 15, 20, 0, tzinfo=ist)  # 45 mins in future

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=future_data_time,
        force=False,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "Causality violation" in reason


def test_validate_forward_capture_force_flag_reclassification():
    """
    Manual pipeline run with force=True is explicitly treated as HISTORICAL_REPLAY.
    """
    ist = ZoneInfo("Asia/Kolkata")
    session_date = date(2026, 4, 15)
    capture_time = datetime(2026, 4, 15, 19, 15, tzinfo=ist)

    mode, reason = validate_forward_capture_evidence(
        session_date=session_date,
        capture_time=capture_time,
        data_as_of=capture_time,
        force=True,
    )

    assert mode == ShadowCaptureMode.HISTORICAL_REPLAY
    assert "force" in reason.lower()


# ==============================================================================
# 4. Shadow Evaluation Immutability Tests
# ==============================================================================


@pytest.mark.django_db
def test_shadow_record_immutability_forward_not_overwritten_by_replay(sample_listing):
    """
    Guarantees that an existing genuine FORWARD_CAPTURED record cannot be
    downgraded or overwritten by a subsequent retrospective replay run.
    """
    import pandas as pd

    service = ShadowEvaluationService()
    session_date = date(2026, 4, 15)

    # 1. Pre-create a genuine FORWARD_CAPTURED record
    forward_rec = MLShadowEvaluationRecord.objects.create(
        listing=sample_listing,
        session_date=session_date,
        setup_name="TREND_PULLBACK_HEURISTIC",
        market_regime="TRENDING_UP",
        risk_level="LOW_RISK",
        is_vetoed=False,
        risk_score=15.0,
        capture_mode=ShadowCaptureMode.FORWARD_CAPTURED,
        decision_captured_at=timezone.now(),
        feature_snapshot_checksum="sha256_forward_original",
    )

    # 2. Replay candidate attempting to overwrite
    df_candidate = pd.DataFrame([{
        "symbol": sample_listing.symbol,
        "session_date": session_date.isoformat(),
        "close_raw": 1500.0,
        "close_adj": 1500.0,
        "sma_50": 1450.0,
        "sma_200": 1400.0,
        "rsi_14": 42.0,
        "stoch_rsi_k": 20.0,
        "atr_14": 25.0,
        "atr_ratio_pct": 1.6,
        "historical_volatility_20": 18.0,
        "bb_bandwidth": 0.08,
        "volume_sma_20": 1000000.0,
        "delivery_pct": 55.0,
        "delivery_pct_sma_20": 50.0,
        "benchmark_rsi_14": 52.0,
        "benchmark_sma_50": 24000.0,
        "benchmark_sma_200": 23000.0,
        "benchmark_close": 24500.0,
        "benchmark_volatility_20": 14.0,
    }])

    # Execute record_session_candidates with force=True (which reclassifies to HISTORICAL_REPLAY)
    recs = service.record_session_candidates(
        df_candidate,
        setup_name="TREND_PULLBACK_HEURISTIC",
        force=True,
    )

    assert len(recs) == 1
    reloaded = MLShadowEvaluationRecord.objects.get(id=forward_rec.id)
    # Must remain FORWARD_CAPTURED and retain original checksum
    assert reloaded.capture_mode == ShadowCaptureMode.FORWARD_CAPTURED
    assert reloaded.feature_snapshot_checksum == "sha256_forward_original"


# ==============================================================================
# 5. Pipeline Health Telemetry & UI Dashboard Tests
# ==============================================================================


@pytest.mark.django_db
def test_pipeline_health_scheduler_installed_awaiting_first_run():
    """
    Validates that when no pipeline executions have occurred, the health state reports
    SCHEDULER_INSTALLED_AWAITING_FIRST_RUN and provides next_expected_session.
    """
    service = ShadowEvaluationService()
    health = service.get_pipeline_health_state()

    assert health["scheduler_status"] == "SCHEDULER_INSTALLED_AWAITING_FIRST_RUN"
    assert health["last_run"] is None
    assert health["next_expected_session"] is not None
    assert isinstance(health["capture_mode_counts"], dict)
    assert health["capture_mode_counts"][ShadowCaptureMode.FORWARD_CAPTURED] == 0


@pytest.mark.django_db
def test_risk_intelligence_dashboard_renders_operational_telemetry(auth_client, sample_listing):
    """
    Validates that the Risk Intelligence dashboard renders the operational telemetry banner,
    displaying Scheduler status, EOD Freshness, and Provenance distribution.
    """
    # Create sample historical candle so page context populates cleanly
    HistoricalCandle.objects.create(
        listing=sample_listing,
        timestamp=timezone.make_aware(datetime(2026, 4, 15, 15, 30)),
        open=1500,
        high=1510,
        low=1490,
        close=1505,
        adjusted_close=1505,
        volume=100000,
        interval="1d",
        source_provider="AUTHENTIC_EOD",
    )

    response = auth_client.get("/ml/risk-dashboard/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    assert "Risk Intelligence &amp; Shadow Validation" in content
    assert "Pipeline:" in content
    assert "Scheduler:" in content
    assert "Provenance Distribution:" in content
    assert "Forward:" in content
    assert "Replay:" in content


@pytest.mark.django_db
def test_risk_intelligence_dashboard_renders_eod_shadow_monitoring_section(auth_client, sample_listing):
    """
    Validates that the Risk Intelligence dashboard renders the dedicated
    'EOD Ingestion & Shadow Pipeline Monitoring' section with actual database-driven
    metrics, separate freshness vs evaluation dates, and statistical risk disclaimers.
    """
    from apps.ml_engine.models import MLShadowPipelineRun, PipelineHealthState

    HistoricalCandle.objects.create(
        listing=sample_listing,
        timestamp=timezone.make_aware(datetime(2026, 11, 23, 15, 30)),
        open=1500,
        high=1510,
        low=1490,
        close=1505,
        adjusted_close=1505,
        volume=100000,
        interval="1d",
        source_provider="JUGAAD",
    )

    MLShadowPipelineRun.objects.create(
        run_id="22222222-3333-4444-5555-666666666666",
        session_date=date(2026, 11, 23),
        status="SUCCESS",
        health_state=PipelineHealthState.HEALTHY,
        trigger_type="MANUAL_CLI",
        started_at=timezone.now(),
        duration_seconds=12.4,
        records_created=2,
    )

    response = auth_client.get("/ml/risk-dashboard/")
    assert response.status_code == 200
    content = response.content.decode("utf-8")

    # 1. Section title and cards
    assert "EOD Ingestion &amp; Shadow Pipeline Monitoring" in content or "EOD Ingestion & Shadow Pipeline Monitoring" in content
    assert "EOD Ingestion Session" in content
    assert "Feature Readiness &amp; Risk Eval" in content
    assert "Last Pipeline Execution" in content
    assert "Shadow Candidates &amp; Outcomes" in content

    # 2. Trigger and mode distinction
    assert "MANUAL CLI" in content

    # 3. Separate dates
    assert "EOD Market Data Freshness:" in content
    assert "risk session date:" in content
    assert "Risk Eval Date:" in content

    # 4. Statistical regime disclaimer
    assert "Regime classification reflects statistical cluster fit, not probability of profitable returns" in content
    assert "denote probability of positive returns" in content


@pytest.mark.django_db
def test_scheduler_status_does_not_claim_operational_without_scheduled_success():
    """
    Validates that scheduler_status never reports 'OPERATIONAL' when only manual CLI
    or registered LaunchAgent configurations exist. Only verified automated SCHEDULED_EOD
    success evidence yields 'OPERATIONAL'.
    """
    from apps.ml_engine.models import MLShadowPipelineRun, PipelineHealthState

    svc = ShadowEvaluationService()

    # Case A: Only MANUAL_CLI runs exist
    MLShadowPipelineRun.objects.create(
        run_id="33333333-4444-5555-6666-777777777777",
        session_date=date(2026, 11, 23),
        status="SUCCESS",
        health_state=PipelineHealthState.HEALTHY,
        trigger_type="MANUAL_CLI",
        started_at=timezone.now(),
    )
    health = svc.get_pipeline_health_state()
    assert health["scheduler_status"] != "OPERATIONAL"
    assert health["scheduler_status"] == "AWAITING_SCHEDULED_RUN"

    # Case B: Verified automated SCHEDULED_EOD run succeeds
    MLShadowPipelineRun.objects.create(
        run_id="44444444-5555-6666-7777-888888888888",
        session_date=date(2026, 11, 24),
        status="SUCCESS",
        health_state=PipelineHealthState.HEALTHY,
        trigger_type="SCHEDULED_EOD",
        started_at=timezone.now(),
    )
    health_scheduled = svc.get_pipeline_health_state()
    assert health_scheduled["scheduler_status"] == "OPERATIONAL"

