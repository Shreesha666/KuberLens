"""
Shadow Evaluation Service for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements transparent forward-looking shadow validation:
1. Captures candidate trading setups on new verified trading sessions.
2. Applies MarketRegimeDetector and MLRiskVetoEngine to assess risk levels point-in-time.
3. Classifies observation provenance: FORWARD_CAPTURED, HISTORICAL_REPLAY, TEST_FIXTURE.
4. Independent per-horizon outcome state machine (5d, 10d, 20d) with separate timestamps and SHA-256 hashes.
5. Deducts realistic Indian market friction (STT, GST, SEBI, Stamp Duty) via IndianTaxCalculator.
6. Computes operational pipeline health states: HEALTHY, WAITING_FOR_DATA, STALE, DEGRADED, FAILED.
7. Detects missed sessions and enables safe, idempotent catch-up recovery.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
from django.db import IntegrityError, OperationalError, models, transaction
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import (
    HorizonMaturityStatus,
    MLModelRecord,
    MLMonitoringEvent,
    MLPipelineLease,
    MLShadowEvaluationRecord,
    MLShadowPipelineRun,
    PipelineHealthState,
    ShadowCaptureMode,
)
from services.calendar.exchange_calendar import ExchangeCalendar
from services.ml.risk_engine import MLRiskVetoEngine, RiskVetoAssessment
from services.paper_trading.tax_calculator import IndianTaxCalculator

logger = logging.getLogger(__name__)


def compute_feature_checksum(features: dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of the feature dictionary.
    Keys are sorted and values normalized to guarantee reproducibility and immutability.
    """
    clean_dict = {}
    for k, v in sorted(features.items()):
        if v is None or pd.isna(v):
            clean_dict[str(k)] = None
        elif isinstance(v, (float, int, Decimal, np.floating, np.integer)):
            if np.isnan(float(v)):
                clean_dict[str(k)] = None
            else:
                clean_dict[str(k)] = round(float(v), 6)
        elif isinstance(v, (list, tuple)):
            clean_dict[str(k)] = [str(x) for x in v]
        elif isinstance(v, dict):
            clean_dict[str(k)] = {str(dk): str(dv) for dk, dv in sorted(v.items())}
        else:
            clean_dict[str(k)] = str(v)

    payload = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_outcome_checksum(outcome_payload: dict[str, Any]) -> str:
    """
    Computes a deterministic SHA-256 hash of the forward price points used to mature returns.
    """
    clean_dict = {}
    for k, v in sorted(outcome_payload.items()):
        if isinstance(v, (float, int, Decimal, np.floating, np.integer)):
            clean_dict[str(k)] = round(float(v), 6)
        else:
            clean_dict[str(k)] = str(v)

    payload = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_net_forward_return(
    entry_open_adj: float,
    exit_close_adj: float,
    entry_open_raw: float | None = None,
    exit_close_raw: float | None = None,
    use_tax_calculator: bool = True,
    slippage_pct: float = 0.0005,
    quantity: int = 100,
) -> float:
    """
    Computes net forward return accounting for entry/exit execution at next-session
    open and exit close with realistic Indian equity CNC transaction friction.
    """
    if entry_open_adj <= 0 or exit_close_adj <= 0:
        return 0.0

    gross_ret = (exit_close_adj - entry_open_adj) / entry_open_adj

    if not use_tax_calculator:
        cost_ratio = 0.0035
    else:
        try:
            entry_p = float(entry_open_raw) if entry_open_raw and entry_open_raw > 0 else entry_open_adj
            exit_p = float(exit_close_raw) if exit_close_raw and exit_close_raw > 0 else exit_close_adj
            buy_charges = IndianTaxCalculator.calculate(
                quantity=quantity,
                price=Decimal(str(round(entry_p, 4))),
                side="BUY",
                product_type="CNC",
            )
            sell_charges = IndianTaxCalculator.calculate(
                quantity=quantity,
                price=Decimal(str(round(exit_p, 4))),
                side="SELL",
                product_type="CNC",
            )
            total_charges = float(buy_charges.total_charges + sell_charges.total_charges)
            turnover = float(entry_p * quantity)
            tax_friction_ratio = total_charges / turnover if turnover > 0 else 0.0025
            cost_ratio = tax_friction_ratio + (2.0 * slippage_pct)
        except Exception as exc:
            logger.debug("Tax friction calculation fallback used: %s", exc)
            cost_ratio = 0.0035

    return gross_ret - cost_ratio


class DatabasePipelineLeaseManager:
    """
    Database-backed distributed lease manager replacing unsafe filesystem lockfiles.
    Provides atomic acquisition, heartbeat renewals, and crash recovery using MLPipelineLease.
    Harden against SQLite multi-process limitations via advisory OS process locks and
    atomic conditional SQL queries.
    """

    DEFAULT_LEASE_DURATION_SECONDS = 600  # 10 minutes

    @classmethod
    @contextmanager
    def _os_process_lock(cls, lease_name: str):
        """
        Advisory OS kernel file lock protecting against SQLite database write contention
        and race conditions across separate processes on the same host.
        """
        lock_path = f"/tmp/kuberlens_lease_{hashlib.md5(lease_name.encode()).hexdigest()[:12]}.lock"
        f = None
        try:
            f = open(lock_path, "w+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX)
            except OSError:
                pass
            yield
        finally:
            if f is not None:
                try:
                    fcntl.flock(f, fcntl.LOCK_UN)
                    f.close()
                except Exception:
                    pass

    @classmethod
    def acquire_lease(
        cls,
        lease_name: str,
        owner_id: str,
        lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Atomically acquires a distributed lease.
        - If no lease exists: creates and acquires it.
        - If active lease held by another owner:
            - If expired (now > expires_at): reclaims/takes over lease (crash recovery).
            - If not expired: returns False (mutual exclusion).
        - If active lease held by same owner: renews heartbeat and extends expiry.
        - If lease is inactive: reactivates and acquires it.
        """
        now = timezone.now()
        expires_at = now + timedelta(seconds=lease_duration_seconds)
        meta = metadata or {}

        with cls._os_process_lock(lease_name):
            with transaction.atomic():
                # 1. Try atomic SQL UPDATE for inactive, expired, or same-owner lease
                # This guarantees that on SQLite or any SQL engine, exactly one process wins
                updated = MLPipelineLease.objects.filter(
                    models.Q(lease_name=lease_name)
                    & (models.Q(is_active=False) | models.Q(expires_at__lt=now) | models.Q(owner_id=owner_id))
                ).update(
                    owner_id=owner_id,
                    acquired_at=now,
                    heartbeat_at=now,
                    expires_at=expires_at,
                    is_active=True,
                    metadata=meta,
                )
                if updated > 0:
                    logger.info("Acquired/renewed lease '%s' for owner '%s'.", lease_name, owner_id)
                    return True

                # 2. If not updated, lease either doesn't exist or is active by another owner
                lease = MLPipelineLease.objects.filter(lease_name=lease_name).first()
                if lease is None:
                    try:
                        MLPipelineLease.objects.create(
                            lease_name=lease_name,
                            owner_id=owner_id,
                            acquired_at=now,
                            heartbeat_at=now,
                            expires_at=expires_at,
                            is_active=True,
                            metadata=meta,
                        )
                        logger.info("Created new lease '%s' for owner '%s'.", lease_name, owner_id)
                        return True
                    except (IntegrityError, OperationalError):
                        # Another process created the lease concurrently
                        logger.warning("Concurrent creation collision for lease '%s'; blocked.", lease_name)
                        return False

                # 3. Lease exists, is active, and has not expired
                logger.warning(
                    "Lease '%s' blocked: currently held by '%s' until %s (heartbeat: %s).",
                    lease_name,
                    lease.owner_id,
                    lease.expires_at,
                    lease.heartbeat_at,
                )
                return False

    @classmethod
    def renew_heartbeat(
        cls,
        lease_name: str,
        owner_id: str,
        extension_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
    ) -> bool:
        """
        Updates heartbeat timestamp and extends expiration time for an active lease.
        """
        now = timezone.now()
        with cls._os_process_lock(lease_name):
            with transaction.atomic():
                updated = MLPipelineLease.objects.filter(
                    lease_name=lease_name,
                    owner_id=owner_id,
                    is_active=True,
                ).update(
                    heartbeat_at=now,
                    expires_at=now + timedelta(seconds=extension_seconds),
                )
                if updated > 0:
                    logger.debug("Heartbeat renewed for lease '%s' by '%s'.", lease_name, owner_id)
                    return True

                logger.warning("Heartbeat renewal failed: lease '%s' not held by owner '%s'.", lease_name, owner_id)
                return False

    @classmethod
    def release_lease(cls, lease_name: str, owner_id: str) -> bool:
        """
        Releases an active lease, marking it inactive.
        """
        with cls._os_process_lock(lease_name):
            with transaction.atomic():
                updated = MLPipelineLease.objects.filter(
                    lease_name=lease_name,
                    owner_id=owner_id,
                    is_active=True,
                ).update(is_active=False)
                if updated > 0:
                    logger.info("Released lease '%s' held by owner '%s'.", lease_name, owner_id)
                    return True

                logger.debug("Release skipped: active lease '%s' not found for owner '%s'.", lease_name, owner_id)
                return False

    @classmethod
    def is_lease_active(cls, lease_name: str) -> bool:
        """
        Returns True if lease exists, is_active=True, and has not expired.
        """
        now = timezone.now()
        return MLPipelineLease.objects.filter(
            lease_name=lease_name,
            is_active=True,
            expires_at__gt=now,
        ).exists()

    @classmethod
    def get_lease_info(cls, lease_name: str) -> dict[str, Any] | None:
        """
        Retrieves detailed information regarding lease state.
        """
        lease = MLPipelineLease.objects.filter(lease_name=lease_name).first()
        if not lease:
            return None

        now = timezone.now()
        is_expired = lease.expires_at <= now
        return {
            "lease_name": lease.lease_name,
            "owner_id": lease.owner_id,
            "acquired_at": lease.acquired_at,
            "heartbeat_at": lease.heartbeat_at,
            "expires_at": lease.expires_at,
            "is_active": lease.is_active and not is_expired,
            "is_expired": is_expired,
            "metadata": lease.metadata,
        }


def validate_forward_capture_evidence(
    session_date: date,
    capture_time: datetime | None = None,
    data_as_of: datetime | None = None,
    force: bool = False,
    requested_mode: str = ShadowCaptureMode.FORWARD_CAPTURED,
) -> tuple[str, str]:
    """
    Evidence-based provenance validation for shadow evaluation observations.
    Evaluates causality, session completion, and lookahead leakage prevention:
    - If requested_mode is not FORWARD_CAPTURED: respects requested mode.
    - If force is True: forced retrospective execution -> HISTORICAL_REPLAY.
    - Trustworthy source ingestion timestamp: data_as_of must be provided.
    - Pre-close source data: data_as_of must be >= 15:30 IST on session_date.
    - Causality check: data_as_of <= capture_time (guards against future clock skew).
    - Session window: capture_time must occur between 15:30 IST on session_date and 09:15 IST on next_trading_day(session_date).
    - If capture_time < 15:30 IST on session_date: pre-close observation -> HISTORICAL_REPLAY.
    - If capture_time >= 09:15 IST on next_trading_day: retrospective observation (future prices visible) -> HISTORICAL_REPLAY.
    - If session_date is not a trading day -> HISTORICAL_REPLAY.
    """
    if requested_mode != ShadowCaptureMode.FORWARD_CAPTURED:
        return requested_mode, f"Requested non-forward capture mode: {requested_mode}."

    if force:
        return ShadowCaptureMode.HISTORICAL_REPLAY, "Manual execution with --force is classified as HISTORICAL_REPLAY."

    ist_tz = ExchangeCalendar.IST
    if capture_time is None:
        capture_time = timezone.now()

    capture_time_ist = capture_time.astimezone(ist_tz) if capture_time.tzinfo else capture_time.replace(tzinfo=ist_tz)

    # 1. Trustworthy Source-Ingestion Timestamp Verification
    if data_as_of is None:
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            "Missing authentic source-ingestion timestamp; unverified provenance reclassified to HISTORICAL_REPLAY.",
        )

    data_as_of_ist = data_as_of.astimezone(ist_tz) if data_as_of.tzinfo else data_as_of.replace(tzinfo=ist_tz)

    # 2. Causality / Clock Skew Check
    if data_as_of_ist > (capture_time_ist + timedelta(seconds=60)):
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            f"Causality violation: data timestamp ({data_as_of_ist.isoformat()}) is after capture time ({capture_time_ist.isoformat()}). Reclassified to HISTORICAL_REPLAY.",
        )

    # 3. Exchange Trading Day Check
    if not ExchangeCalendar.is_trading_day(session_date):
        holiday = ExchangeCalendar.get_holiday_reason(session_date) or "Non-Trading Day / Weekend"
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            f"Session date {session_date} is not an exchange trading day ({holiday}). Reclassified to HISTORICAL_REPLAY.",
        )

    # 4. Post-Market Permissible Window Check
    session_close_ist = datetime.combine(session_date, ExchangeCalendar.MARKET_CLOSE_TIME).replace(tzinfo=ist_tz)
    next_session = ExchangeCalendar.get_next_trading_day(session_date)
    next_session_open_ist = datetime.combine(next_session, ExchangeCalendar.MARKET_OPEN_TIME).replace(tzinfo=ist_tz)

    if capture_time_ist < session_close_ist:
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            f"Pre-close capture: capture time {capture_time_ist.strftime('%Y-%m-%d %H:%M:%S')} IST is before session close at 15:30 IST. Reclassified to HISTORICAL_REPLAY.",
        )

    # Source data must have been ingested after market close for that session
    if data_as_of_ist < session_close_ist:
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            f"Pre-close source data: data ingestion timestamp ({data_as_of_ist.strftime('%Y-%m-%d %H:%M:%S')} IST) is before session close (15:30 IST); incomplete market data. Reclassified to HISTORICAL_REPLAY.",
        )

    if capture_time_ist >= next_session_open_ist:
        return (
            ShadowCaptureMode.HISTORICAL_REPLAY,
            f"Retrospective capture: capture time {capture_time_ist.strftime('%Y-%m-%d %H:%M:%S')} IST is after next session open ({next_session} 09:15 IST); next prices observable. Reclassified to HISTORICAL_REPLAY.",
        )

    return ShadowCaptureMode.FORWARD_CAPTURED, "Valid post-market forward capture window."


class ShadowEvaluationService:
    """
    Manages point-in-time shadow evaluations, data integrity checks,
    per-horizon state machines, and forward outcome maturation.
    """

    def __init__(self, risk_engine: MLRiskVetoEngine | None = None):
        self.risk_engine = risk_engine or MLRiskVetoEngine()
        self.last_maturation_stats: dict[str, int] = {
            "matured_5d": 0,
            "matured_10d": 0,
            "matured_20d": 0,
            "total_updated": 0,
        }

    def validate_session_readiness(
        self,
        session_date: date,
        required_symbols: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Validates whether session_date is eligible for EOD shadow evaluation:
        1. Exchange trading day check.
        2. Market close check (>= 15:30 IST if today).
        3. Candle data freshness and provenance in HistoricalCandle (always enforced).
        4. Benchmark (^NSEI) candle existence.
        5. Universe symbol completeness.
        """
        result: dict[str, Any] = {
            "session_date": session_date,
            "status": "WAITING_FOR_DATA",
            "is_ready": False,
            "is_trading_day": False,
            "holiday_reason": None,
            "market_closed": False,
            "benchmark_available": False,
            "candle_count": 0,
            "symbols_found": 0,
            "missing_symbols": [],
            "reason": "",
        }

        # 1. Trading Day Check
        is_trading = ExchangeCalendar.is_trading_day(session_date)
        result["is_trading_day"] = is_trading
        if not is_trading:
            holiday = ExchangeCalendar.get_holiday_reason(session_date) or "Weekend"
            result["holiday_reason"] = holiday
            result["status"] = "SKIPPED_HOLIDAY"
            result["reason"] = f"Date {session_date} is not an exchange trading day ({holiday})."
            if not force:
                return result

        # 2. Market Close Check (if today)
        now_ist = datetime.now(ExchangeCalendar.IST)
        if session_date == now_ist.date() and not force:
            if now_ist.time() < ExchangeCalendar.MARKET_CLOSE_TIME:
                result["market_closed"] = False
                result["status"] = "WAITING_FOR_DATA"
                result["reason"] = f"Market session for {session_date} is still open (current IST: {now_ist.time().strftime('%H:%M:%S')})."
                return result
        result["market_closed"] = True

        # 3. Market Data Freshness (HistoricalCandle presence is mandatory; 0 candles always yields is_ready=False)
        candles_qs = HistoricalCandle.objects.filter(
            timestamp__date=session_date,
            interval="1d",
        )
        candle_count = candles_qs.count()
        result["candle_count"] = candle_count

        if candle_count == 0:
            result["status"] = "WAITING_FOR_DATA" if session_date >= (now_ist.date() - timedelta(days=2)) else "FAILED"
            result["reason"] = f"No 1d historical candles found for session date {session_date}."
            result["is_ready"] = False
            return result

        # 4. Benchmark Check (^NSEI)
        benchmark_exists = candles_qs.filter(listing__symbol="^NSEI").exists()
        result["benchmark_available"] = benchmark_exists
        if not benchmark_exists:
            result["status"] = "DEGRADED"
            result["reason"] = f"Benchmark index candle (^NSEI) missing for session date {session_date}."
            if not force:
                result["is_ready"] = False
                return result

        # 5. Required Symbols Check
        if required_symbols:
            present_symbols = set(
                candles_qs.filter(listing__symbol__in=required_symbols).values_list("listing__symbol", flat=True)
            )
            missing = [s for s in required_symbols if s not in present_symbols]
            result["symbols_found"] = len(present_symbols)
            result["missing_symbols"] = missing
            if len(present_symbols) < len(required_symbols) * 0.5:
                result["status"] = "DEGRADED"
                result["reason"] = f"Insufficient market data: found {len(present_symbols)}/{len(required_symbols)} symbols."
                if not force:
                    result["is_ready"] = False
                    return result
            elif missing:
                result["status"] = "DEGRADED"
                result["reason"] = f"Partial market data: missing {len(missing)}/{len(required_symbols)} symbols: {', '.join(missing)}."

        # 6. Provider Provenance & Authentic Ingestion Freshness
        providers = list(candles_qs.values_list("source_provider", flat=True).distinct())
        latest_ingestion = candles_qs.aggregate(models.Max("retrieved_at"))["retrieved_at__max"]
        result["source_providers"] = providers
        result["latest_source_ingestion"] = latest_ingestion

        if not result["missing_symbols"] and benchmark_exists:
            result["status"] = "SUCCESS"
            result["reason"] = "Session is ready for shadow pipeline evaluation."

        result["is_ready"] = True
        return result

    def record_session_candidates(
        self,
        df_feature_row_candidates: pd.DataFrame,
        setup_name: str = "TREND_PULLBACK_HEURISTIC",
        source_provider: str = "AUTHENTIC_EOD",
        actual_data_as_of: datetime | None = None,
        capture_mode: str = ShadowCaptureMode.FORWARD_CAPTURED,
        processing_run_id: uuid.UUID | None = None,
        force: bool = False,
    ) -> list[MLShadowEvaluationRecord]:
        """
        Takes candidate setup rows for session date t, evaluates them via risk veto,
        and records them into MLShadowEvaluationRecord with SHA-256 feature checksums
        under transactional concurrency protection.

        Integrity Safeguards:
        - Validates genuine causality and post-market execution window via validate_forward_capture_evidence.
        - Captures before 15:30 IST or after 09:15 IST of next trading session are reclassified to HISTORICAL_REPLAY.
        - Retrospective force runs (--force) are reclassified to HISTORICAL_REPLAY.
        - Existing genuine FORWARD_CAPTURED records are immutable and cannot be overwritten or downgraded by replays.
        - Matured records are preserved and never modified by subsequent candidate recording.
        """
        if df_feature_row_candidates.empty:
            return []

        now_utc = timezone.now()
        if actual_data_as_of is None:
            actual_data_as_of = now_utc

        if processing_run_id is None:
            processing_run_id = uuid.uuid4()

        records = []

        with transaction.atomic():
            for _, row in df_feature_row_candidates.iterrows():
                sym = str(row["symbol"])
                listing = ExchangeListing.objects.filter(symbol=sym).first()
                if not listing:
                    continue

                assessment: RiskVetoAssessment = self.risk_engine.assess_setup(row)
                sdate = row["session_date"]
                if isinstance(sdate, str):
                    sdate = date.fromisoformat(sdate)

                feature_checksum = compute_feature_checksum(assessment.metrics)

                # Source ingestion timestamp & provider verification from database
                row_data_as_of = actual_data_as_of
                row_provider = source_provider
                candle_qs = HistoricalCandle.objects.filter(listing=listing, timestamp__date=sdate, interval="1d")
                candle_ts = candle_qs.aggregate(models.Max("retrieved_at"))["retrieved_at__max"]
                if row_data_as_of is None and candle_ts is not None:
                    row_data_as_of = candle_ts
                candle_prov = candle_qs.values_list("source_provider", flat=True).first()
                if candle_prov:
                    row_provider = candle_prov

                # Validate genuine forward capture evidence vs historical replay
                effective_capture_mode, audit_note = validate_forward_capture_evidence(
                    session_date=sdate,
                    capture_time=now_utc,
                    data_as_of=row_data_as_of,
                    force=force,
                    requested_mode=capture_mode,
                )

                if audit_note and effective_capture_mode != capture_mode:
                    logger.warning(
                        "Observation for %s on %s reclassified from %s to %s: %s",
                        sym,
                        sdate,
                        capture_mode,
                        effective_capture_mode,
                        audit_note,
                    )

                # Check if an existing record exists with row-level lock
                existing = (
                    MLShadowEvaluationRecord.objects.select_for_update()
                    .filter(listing=listing, session_date=sdate, setup_name=setup_name)
                    .first()
                )

                if existing:
                    # Immutability Protection:
                    # 1. Do not overwrite already matured records; preserve historical integrity
                    if existing.is_matured:
                        records.append(existing)
                        continue
                    # 2. Never allow a historical replay to overwrite/downgrade an authentic FORWARD_CAPTURED record
                    if (
                        existing.capture_mode == ShadowCaptureMode.FORWARD_CAPTURED
                        and effective_capture_mode == ShadowCaptureMode.HISTORICAL_REPLAY
                    ):
                        logger.info(
                            "Preserved existing immutable FORWARD_CAPTURED record for %s on %s (replay rejected).",
                            sym,
                            sdate,
                        )
                        records.append(existing)
                        continue

                defaults = {
                    "market_regime": assessment.regime.value,
                    "risk_level": assessment.risk_level.value,
                    "is_vetoed": assessment.is_vetoed,
                    "risk_score": Decimal(str(assessment.risk_score)),
                    "veto_reasons": assessment.veto_reasons,
                    "features_snapshot": assessment.metrics,
                    "model_version": "v1.0-risk-veto",
                    "evaluation_mode": "SHADOW_RESEARCH_ONLY",
                    "actual_data_as_of": row_data_as_of or now_utc,
                    "feature_schema_version": "feat-v2.1.0",
                    "feature_snapshot_checksum": feature_checksum,
                    "source_provider": row_provider,
                    "decision_status": "PENDING_MATURATION",
                    "capture_mode": effective_capture_mode,
                    "decision_captured_at": now_utc,
                    "processing_run_id": processing_run_id,
                    "error_message": audit_note,
                }

                rec, _ = MLShadowEvaluationRecord.objects.update_or_create(
                    listing=listing,
                    session_date=sdate,
                    setup_name=setup_name,
                    defaults=defaults,
                )
                records.append(rec)

        return records

    def mature_pending_evaluations(
        self,
        canonical_price_df: pd.DataFrame,
        as_of_session: date | None = None,
        use_tax_calculator: bool = True,
    ) -> int:
        """
        Matures forward outcomes for pending shadow evaluation records.
        Implements an independent state machine per horizon (5d, 10d, 20d):
        - A 5d result maturing does NOT cause a 20d result to be marked mature.
        - Stores independent maturity timestamps and SHA-256 price checksums.
        - Calculates realistic net returns with IndianTaxCalculator friction.
        """
        if canonical_price_df.empty:
            return 0

        canonical_price_df = canonical_price_df.drop_duplicates(subset=["session_date", "symbol"], keep="last")
        all_dates = sorted(canonical_price_df["session_date"].unique())
        date_to_idx = {d: i for i, d in enumerate(all_dates)}
        prices = canonical_price_df.set_index(["session_date", "symbol"]).sort_index()

        pending = MLShadowEvaluationRecord.objects.filter(is_matured=False)
        matured_5d_cnt = 0
        matured_10d_cnt = 0
        matured_20d_cnt = 0
        total_records_updated = 0

        now = timezone.now()

        with transaction.atomic():
            for rec in pending:
                sdate_str = rec.session_date.isoformat()
                if sdate_str not in date_to_idx:
                    continue
                cur_idx = date_to_idx[sdate_str]
                next_idx = cur_idx + 1
                if next_idx >= len(all_dates):
                    continue  # Next open not yet occurred

                next_date = all_dates[next_idx]
                try:
                    price_row_next = prices.loc[(next_date, rec.listing.symbol)]
                    if isinstance(price_row_next, pd.DataFrame):
                        price_row_next = price_row_next.iloc[-1]
                    open_next_adj = float(price_row_next["open_adj"])
                    open_next_raw = (
                        float(price_row_next["open_raw"]) if "open_raw" in price_row_next else open_next_adj
                    )
                except KeyError:
                    continue

                if open_next_adj <= 0:
                    continue

                record_changed = False

                # 1. Independent 5-Session Horizon State Machine
                if rec.status_5d == HorizonMaturityStatus.PENDING:
                    h5_idx = cur_idx + 5
                    if h5_idx < len(all_dates):
                        h5_date = all_dates[h5_idx]
                        try:
                            p5 = prices.loc[(h5_date, rec.listing.symbol)]
                            if isinstance(p5, pd.DataFrame):
                                p5 = p5.iloc[-1]
                            c5_adj = float(p5["close_adj"])
                            c5_raw = float(p5["close_raw"]) if "close_raw" in p5 else c5_adj
                            net_5d = compute_net_forward_return(
                                open_next_adj, c5_adj, open_next_raw, c5_raw, use_tax_calculator=use_tax_calculator
                            )
                            rec.forward_return_5d = Decimal(str(round(net_5d, 4)))
                            rec.status_5d = HorizonMaturityStatus.MATURED
                            rec.matured_at_5d = now
                            rec.source_checksum_5d = compute_outcome_checksum({
                                "entry_date": next_date,
                                "entry_open_adj": open_next_adj,
                                "exit_5d_date": h5_date,
                                "exit_5d_close_adj": c5_adj,
                                "forward_return_5d": round(net_5d, 4),
                            })
                            matured_5d_cnt += 1
                            record_changed = True
                        except KeyError:
                            pass

                # 2. Independent 10-Session Horizon State Machine
                if rec.status_10d == HorizonMaturityStatus.PENDING:
                    h10_idx = cur_idx + 10
                    if h10_idx < len(all_dates):
                        h10_date = all_dates[h10_idx]
                        try:
                            p10 = prices.loc[(h10_date, rec.listing.symbol)]
                            if isinstance(p10, pd.DataFrame):
                                p10 = p10.iloc[-1]
                            c10_adj = float(p10["close_adj"])
                            c10_raw = float(p10["close_raw"]) if "close_raw" in p10 else c10_adj
                            net_10d = compute_net_forward_return(
                                open_next_adj, c10_adj, open_next_raw, c10_raw, use_tax_calculator=use_tax_calculator
                            )
                            rec.forward_return_10d = Decimal(str(round(net_10d, 4)))
                            rec.status_10d = HorizonMaturityStatus.MATURED
                            rec.matured_at_10d = now
                            rec.source_checksum_10d = compute_outcome_checksum({
                                "entry_date": next_date,
                                "entry_open_adj": open_next_adj,
                                "exit_10d_date": h10_date,
                                "exit_10d_close_adj": c10_adj,
                                "forward_return_10d": round(net_10d, 4),
                            })
                            matured_10d_cnt += 1
                            record_changed = True
                        except KeyError:
                            pass

                # 3. Independent 20-Session Horizon State Machine (Full Maturation)
                if rec.status_20d == HorizonMaturityStatus.PENDING:
                    h20_idx = cur_idx + 20
                    if h20_idx < len(all_dates):
                        h20_date = all_dates[h20_idx]
                        try:
                            p20 = prices.loc[(h20_date, rec.listing.symbol)]
                            if isinstance(p20, pd.DataFrame):
                                p20 = p20.iloc[-1]
                            c20_adj = float(p20["close_adj"])
                            c20_raw = float(p20["close_raw"]) if "close_raw" in p20 else c20_adj
                            net_20d = compute_net_forward_return(
                                open_next_adj, c20_adj, open_next_raw, c20_raw, use_tax_calculator=use_tax_calculator
                            )
                            rec.forward_return_20d = Decimal(str(round(net_20d, 4)))
                            rec.status_20d = HorizonMaturityStatus.MATURED
                            rec.matured_at_20d = now
                            rec.source_checksum_20d = compute_outcome_checksum({
                                "entry_date": next_date,
                                "entry_open_adj": open_next_adj,
                                "exit_20d_date": h20_date,
                                "exit_20d_close_adj": c20_adj,
                                "forward_return_20d": round(net_20d, 4),
                            })

                            rec.is_matured = True
                            rec.decision_status = "MATURED"
                            rec.outcome_matured_at = now
                            rec.outcome_source_checksum = rec.source_checksum_20d
                            matured_20d_cnt += 1
                            record_changed = True
                        except KeyError:
                            pass

                if record_changed:
                    rec.save()
                    total_records_updated += 1

        self.last_maturation_stats = {
            "matured_5d": matured_5d_cnt,
            "matured_10d": matured_10d_cnt,
            "matured_20d": matured_20d_cnt,
            "total_updated": total_records_updated,
        }
        # Return total distinct records matured or updated for compatibility
        return total_records_updated

    def compute_shadow_summary(self, forward_only: bool = True) -> dict[str, Any]:
        """
        Computes summary statistics comparing accepted vs vetoed setups.
        By default, evaluates strictly genuine forward captured observations
        (capture_mode='FORWARD_CAPTURED') to prevent backfill contamination.
        """
        all_qs = MLShadowEvaluationRecord.objects.all()

        if forward_only:
            # Genuine forward shadow records only
            eval_qs = all_qs.filter(capture_mode=ShadowCaptureMode.FORWARD_CAPTURED)
        else:
            eval_qs = all_qs

        total_evals = eval_qs.count()
        matured = eval_qs.filter(is_matured=True)
        total_matured = matured.count()
        pending_count = eval_qs.filter(is_matured=False).count()

        # Capture mode distribution across all records
        mode_dist: dict[str, int] = {}
        for row in all_qs.values("capture_mode"):
            mode = row["capture_mode"]
            mode_dist[mode] = mode_dist.get(mode, 0) + 1

        # Per-horizon maturation counts
        matured_5d = eval_qs.filter(status_5d=HorizonMaturityStatus.MATURED).count()
        matured_10d = eval_qs.filter(status_10d=HorizonMaturityStatus.MATURED).count()
        matured_20d = eval_qs.filter(status_20d=HorizonMaturityStatus.MATURED).count()

        if total_matured == 0:
            return {
                "total_evaluations": total_evals,
                "matured_evaluations": 0,
                "pending_evaluations": pending_count,
                "accepted_count": eval_qs.filter(is_vetoed=False).count(),
                "vetoed_count": eval_qs.filter(is_vetoed=True).count(),
                "accepted_mean_return_20d_pct": 0.0,
                "vetoed_mean_return_20d_pct": 0.0,
                "veto_alpha_spread_pct": 0.0,
                "risk_tier_distribution": {},
                "status_distribution": {},
                "matured_5d_count": matured_5d,
                "matured_10d_count": matured_10d,
                "matured_20d_count": matured_20d,
                "capture_mode_distribution": mode_dist,
                "forward_only": forward_only,
            }

        accepted = matured.filter(is_vetoed=False)
        vetoed = matured.filter(is_vetoed=True)

        acc_rets = [float(r.forward_return_20d) for r in accepted if r.forward_return_20d is not None]
        vet_rets = [float(r.forward_return_20d) for r in vetoed if r.forward_return_20d is not None]

        acc_mean = (sum(acc_rets) / len(acc_rets) * 100.0) if acc_rets else 0.0
        vet_mean = (sum(vet_rets) / len(vet_rets) * 100.0) if vet_rets else 0.0
        spread = round(acc_mean - vet_mean, 2)

        risk_dist: dict[str, int] = {}
        status_dist: dict[str, int] = {}
        for r in eval_qs:
            risk_dist[r.risk_level] = risk_dist.get(r.risk_level, 0) + 1
            status_dist[r.decision_status] = status_dist.get(r.decision_status, 0) + 1

        return {
            "total_evaluations": total_evals,
            "matured_evaluations": total_matured,
            "pending_evaluations": pending_count,
            "accepted_count": accepted.count(),
            "vetoed_count": vetoed.count(),
            "accepted_mean_return_20d_pct": round(acc_mean, 2),
            "vetoed_mean_return_20d_pct": round(vet_mean, 2),
            "veto_alpha_spread_pct": spread,
            "risk_tier_distribution": risk_dist,
            "status_distribution": status_dist,
            "matured_5d_count": matured_5d,
            "matured_10d_count": matured_10d,
            "matured_20d_count": matured_20d,
            "capture_mode_distribution": mode_dist,
            "forward_only": forward_only,
        }

    def detect_missed_sessions(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[date]:
        """
        Detects un-evaluated trading days between from_date and to_date.
        Defaults to checking the window between the last successful pipeline run
        and the latest completed exchange session.
        """
        if to_date is None:
            to_date = ExchangeCalendar.get_last_trading_day()

        if from_date is None:
            last_run = MLShadowPipelineRun.objects.filter(status="SUCCESS").order_by("-session_date").first()
            if last_run:
                from_date = last_run.session_date + timedelta(days=1)
            else:
                from_date = to_date - timedelta(days=7)

        if from_date > to_date:
            return []

        trading_days = ExchangeCalendar.get_trading_days(from_date, to_date)
        if not trading_days:
            return []

        # Find trading days that already have records or successful pipeline runs
        existing_run_dates = set(
            MLShadowPipelineRun.objects.filter(
                session_date__in=trading_days,
                status="SUCCESS",
            ).values_list("session_date", flat=True)
        )
        existing_eval_dates = set(
            MLShadowEvaluationRecord.objects.filter(
                session_date__in=trading_days,
            ).values_list("session_date", flat=True)
        )

        evaluated_dates = existing_run_dates | existing_eval_dates
        missed = [d for d in trading_days if d not in evaluated_dates]
        return missed

    def get_pipeline_health_state(self) -> dict[str, Any]:
        """
        Derives real-time operational health state from persisted pipeline runs:
        - HEALTHY: Recent successful run within operational trading window.
        - WAITING_FOR_DATA: Market closed or last session missing candles.
        - STALE: No successful run for > 2 trading sessions.
        - DEGRADED: Last run had partial warnings or incomplete data.
        - FAILED: Last run resulted in an uncaught error.
        """
        last_run = MLShadowPipelineRun.objects.order_by("-started_at").first()
        last_success = MLShadowPipelineRun.objects.filter(status="SUCCESS").order_by("-started_at").first()
        last_failed = MLShadowPipelineRun.objects.filter(status="FAILED").order_by("-started_at").first()

        now_utc = timezone.now()
        now_ist = datetime.now(ExchangeCalendar.IST)
        today = now_ist.date()

        health_state = PipelineHealthState.HEALTHY
        reason = "Pipeline is operating normally."
        retry_count = 0

        if last_run:
            retry_count = last_run.retry_count
            if last_run.status == "WAITING_FOR_DATA":
                health_state = PipelineHealthState.WAITING_FOR_DATA
                reason = last_run.error_details or f"Awaiting market data ingestion for session {last_run.session_date}."
            elif last_run.status == "DEGRADED":
                health_state = PipelineHealthState.DEGRADED
                reason = last_run.error_details or f"Pipeline ran in DEGRADED data mode on session {last_run.session_date}."
            elif last_run.status == "FAILED":
                health_state = PipelineHealthState.FAILED
                reason = f"Last pipeline run failed: {last_run.error_details}"

        if last_failed and (not last_success or last_failed.started_at > last_success.started_at):
            health_state = PipelineHealthState.FAILED
            reason = f"Last pipeline run failed: {last_failed.error_details}"
        elif not last_success and health_state == PipelineHealthState.HEALTHY:
            health_state = PipelineHealthState.STALE
            reason = "No successful pipeline runs recorded."
        elif last_success and health_state == PipelineHealthState.HEALTHY:
            # Check data freshness age
            age_hours = (now_utc - last_success.started_at).total_seconds() / 3600.0
            last_trading = ExchangeCalendar.get_last_trading_day(today)

            if today == last_trading and now_ist.time() >= ExchangeCalendar.MARKET_CLOSE_TIME:
                candle_count = HistoricalCandle.objects.filter(timestamp__date=today, interval="1d").count()
                if candle_count == 0:
                    health_state = PipelineHealthState.WAITING_FOR_DATA
                    reason = f"Market session {today} closed at 15:30 IST; awaiting EOD data ingestion."
                elif last_success.session_date < today:
                    health_state = PipelineHealthState.WAITING_FOR_DATA
                    reason = f"Fresh data available for {today}; awaiting automated EOD pipeline cycle."
            elif age_hours > 72.0:  # > 3 calendar days (accounting for weekend)
                health_state = PipelineHealthState.STALE
                reason = f"Pipeline execution is stale (last run {round(age_hours, 1)}h ago)."

        missed = self.detect_missed_sessions()

        # Operational scheduler verdict & health state
        # Never show OPERATIONAL solely because scheduler is registered!
        has_scheduled_run = MLShadowPipelineRun.objects.filter(
            trigger_type__in=["SCHEDULED_EOD", "SCHEDULED"],
            status="SUCCESS",
        ).exists()

        if not last_run:
            scheduler_status = "SCHEDULER_INSTALLED_AWAITING_FIRST_RUN"
        elif not has_scheduled_run and last_run.trigger_type in ["MANUAL_CLI", "MANUAL"]:
            scheduler_status = "AWAITING_SCHEDULED_RUN"
        elif health_state == PipelineHealthState.FAILED:
            scheduler_status = "ATTENTION_REQUIRED"
        elif health_state == PipelineHealthState.WAITING_FOR_DATA:
            scheduler_status = "WAITING_FOR_DATA"
        elif health_state == PipelineHealthState.DEGRADED:
            scheduler_status = "DEGRADED"
        elif health_state == PipelineHealthState.STALE:
            scheduler_status = "STALE"
        elif health_state == PipelineHealthState.HEALTHY:
            scheduler_status = "OPERATIONAL" if has_scheduled_run else "AWAITING_SCHEDULED_RUN"
        else:
            scheduler_status = health_state.value if hasattr(health_state, "value") else str(health_state)

        # Next expected exchange session
        base_date = today if ExchangeCalendar.is_trading_day(today) else ExchangeCalendar.get_last_trading_day(today)
        next_expected_session = ExchangeCalendar.get_next_trading_day(base_date)

        # Active distributed pipeline lease
        active_lease = DatabasePipelineLeaseManager.get_lease_info("SHADOW_EOD_PIPELINE")

        # Provenance distribution counts
        mode_counts = {
            ShadowCaptureMode.FORWARD_CAPTURED: MLShadowEvaluationRecord.objects.filter(
                capture_mode=ShadowCaptureMode.FORWARD_CAPTURED
            ).count(),
            ShadowCaptureMode.HISTORICAL_REPLAY: MLShadowEvaluationRecord.objects.filter(
                capture_mode=ShadowCaptureMode.HISTORICAL_REPLAY
            ).count(),
            ShadowCaptureMode.TEST_FIXTURE: MLShadowEvaluationRecord.objects.filter(
                capture_mode=ShadowCaptureMode.TEST_FIXTURE
            ).count(),
        }

        freshness_age_hours = (
            round((now_utc - last_success.started_at).total_seconds() / 3600.0, 1) if last_success else None
        )

        return {
            "health_state": health_state.value if hasattr(health_state, "value") else str(health_state),
            "reason": reason,
            "last_run": last_run,
            "last_successful_run": last_success,
            "last_failed_run": last_failed,
            "retry_count": retry_count,
            "missed_sessions": [d.isoformat() for d in missed],
            "missed_sessions_count": len(missed),
            "data_freshness_date": last_success.session_date if last_success else None,
            "data_freshness_age_hours": freshness_age_hours,
            "scheduler_status": scheduler_status,
            "next_expected_session": next_expected_session.isoformat() if next_expected_session else None,
            "active_lease": active_lease,
            "capture_mode_counts": mode_counts,
        }

    def record_pipeline_event(
        self,
        event_type: str,
        severity: str,
        details: dict[str, Any],
        model_record: MLModelRecord | None = None,
        cooldown_minutes: int = 60,
    ) -> MLMonitoringEvent | None:
        """
        Logs an operational monitoring event with cooldown deduplication
        to prevent alert fatigue.
        """
        now = timezone.now()
        cooldown_threshold = now - timedelta(minutes=cooldown_minutes)

        # Check for duplicate event within cooldown window
        recent_duplicate = MLMonitoringEvent.objects.filter(
            event_type=event_type,
            severity=severity,
            created_at__gte=cooldown_threshold,
        ).first()

        if recent_duplicate:
            logger.debug("Suppressed duplicate %s event within %d-minute cooldown.", event_type, cooldown_minutes)
            return recent_duplicate

        return MLMonitoringEvent.objects.create(
            model_record=model_record,
            event_type=event_type,
            severity=severity,
            details=details,
        )
