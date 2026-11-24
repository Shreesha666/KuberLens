"""
End-of-Day Shadow Monitoring Pipeline Management Command.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Orchestrates daily automated shadow risk evaluation:
1. Validates exchange trading calendar and market session close (15:30 IST).
2. Verifies market data freshness and ^NSEI benchmark provenance.
3. Builds point-in-time canonical features and identifies candidate setups.
4. Executes explainable risk-veto classifications point-in-time.
5. Persists immutable shadow records with cryptographic SHA-256 checksums and capture classification.
6. Matures forward outcomes (5d, 10d, 20d) via independent per-horizon state machine.
7. Logs operational health and drift metrics into MLMonitoringEvent and MLShadowPipelineRun.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import date, timedelta
from typing import Any

from django.core.management.base import BaseCommand
from django.db import models
from django.utils import timezone

from apps.market.models import HistoricalCandle
from apps.ml_engine.models import (
    MLModelRecord,
    MLShadowPipelineRun,
    PipelineHealthState,
    ShadowCaptureMode,
)
from apps.ml_engine.views import PILOT_SYMBOLS
from services.calendar.exchange_calendar import ExchangeCalendar
from services.ml.dataset_builder import DatasetBuilder
from services.ml.features import FeaturePipeline
from services.ml.risk_engine import MLRiskVetoEngine
from services.ml.shadow_service import DatabasePipelineLeaseManager, ShadowEvaluationService

PIPELINE_LOCK_FILE = "/tmp/kuberlens_shadow_pipeline.lock"
PIPELINE_LEASE_NAME = "SHADOW_EOD_PIPELINE"


class Command(BaseCommand):
    help = (
        "Runs the automated End-of-Day (EOD) Risk Intelligence & Shadow Evaluation pipeline. "
        "Validates session completion, checks market data freshness, evaluates setup candidates "
        "in research-only shadow mode, persists SHA-256 checksummed decisions, and matures past outcomes."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--session-date",
            type=str,
            default=None,
            help="Session date to evaluate (YYYY-MM-DD). Defaults to latest trading day.",
        )
        parser.add_argument(
            "--universe",
            type=str,
            default=None,
            help="Comma-separated listing symbols. Defaults to PILOT_SYMBOLS (11 equities).",
        )
        parser.add_argument(
            "--setup-name",
            type=str,
            default="TREND_PULLBACK_HEURISTIC",
            help="Trading setup identifier being shadow evaluated.",
        )
        parser.add_argument(
            "--lookback-days",
            type=int,
            default=365,
            help="Calendar days of historical lookback for feature pipeline calculation (default 365).",
        )
        parser.add_argument(
            "--capture-mode",
            type=str,
            default=ShadowCaptureMode.FORWARD_CAPTURED,
            choices=[
                ShadowCaptureMode.FORWARD_CAPTURED,
                ShadowCaptureMode.HISTORICAL_REPLAY,
                ShadowCaptureMode.TEST_FIXTURE,
            ],
            help="Observation provenance classification (default FORWARD_CAPTURED).",
        )
        parser.add_argument(
            "--ingest-eod",
            action="store_true",
            default=False,
            help="Automatically execute authentic EOD market data ingestion before evaluation.",
        )
        parser.add_argument(
            "--catchup-missed",
            action="store_true",
            default=False,
            help="Automatically detect and sequentially execute missed trading sessions.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Force pipeline execution even on holidays, weekends, or before session close.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Perform all validation and risk assessments without saving shadow records or events.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        start_time = time.time()
        run_uuid = uuid.uuid4()
        owner_id = str(run_uuid)
        self.stdout.write(self.style.MIGRATE_HEADING("=== KuberLens AI/ML: EOD Shadow Evaluation Pipeline ==="))

        # Concurrency Protection: Legacy Filesystem Lock Check (Backward Compatibility)
        if os.path.exists(PIPELINE_LOCK_FILE) and not options["dry_run"] and not options["force"]:
            try:
                mtime = os.path.getmtime(PIPELINE_LOCK_FILE)
                if (time.time() - mtime) < 900:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Concurrent execution blocked: lockfile {PIPELINE_LOCK_FILE} active. Another pipeline run is in progress."
                        )
                    )
                    return
                else:
                    self.stdout.write(self.style.WARNING("Removing stale lockfile from previous interrupted run."))
                    os.remove(PIPELINE_LOCK_FILE)
            except OSError:
                pass

        # Concurrency Protection via Database Lease Manager
        lease_acquired = False
        if not options["dry_run"] and not options["force"]:
            lease_acquired = DatabasePipelineLeaseManager.acquire_lease(
                lease_name=PIPELINE_LEASE_NAME,
                owner_id=owner_id,
                lease_duration_seconds=900,
                metadata={
                    "command": "run_shadow_eod_pipeline",
                    "pid": os.getpid(),
                    "requested_session": str(options.get("session_date")),
                },
            )
            if not lease_acquired:
                lease_info = DatabasePipelineLeaseManager.get_lease_info(PIPELINE_LEASE_NAME)
                held_by = lease_info.get("owner_id") if lease_info else "unknown"
                expires = lease_info.get("expires_at") if lease_info else "unknown"
                self.stderr.write(
                    self.style.ERROR(
                        f"Concurrent execution blocked: lease '{PIPELINE_LEASE_NAME}' held by '{held_by}' until {expires}."
                    )
                )
                return
        elif not options["dry_run"] and options["force"]:
            # Forced execution acquires lease unconditionally
            lease_acquired = DatabasePipelineLeaseManager.acquire_lease(
                lease_name=PIPELINE_LEASE_NAME,
                owner_id=owner_id,
                lease_duration_seconds=900,
                metadata={"command": "run_shadow_eod_pipeline", "pid": os.getpid(), "forced": True},
            )

        shadow_svc = ShadowEvaluationService(risk_engine=MLRiskVetoEngine())

        # Check missed sessions if catchup requested
        if options["catchup_missed"]:
            missed = shadow_svc.detect_missed_sessions()
            if missed:
                self.stdout.write(self.style.NOTICE(f"Detected {len(missed)} missed session(s): {', '.join(d.isoformat() for d in missed)}"))
                for missed_date in missed:
                    self.stdout.write(f"\n--- Catching up missed session: {missed_date} ---")
                    catchup_opts = options.copy()
                    catchup_opts["session_date"] = missed_date.isoformat()
                    catchup_opts["catchup_missed"] = False
                    # Past session close check passes naturally; genuine data readiness must be enforced
                    catchup_opts["force"] = False
                    catchup_opts["capture_mode"] = ShadowCaptureMode.HISTORICAL_REPLAY  # Missed catch-up is historical replay
                    self._execute_session_pipeline(
                        missed_date,
                        shadow_svc,
                        catchup_opts,
                        run_uuid=uuid.uuid4(),
                        owner_id=owner_id,
                    )
                self.stdout.write(self.style.SUCCESS("\nAll missed sessions catchup sequence completed."))
                if not options["dry_run"] and lease_acquired:
                    DatabasePipelineLeaseManager.release_lease(PIPELINE_LEASE_NAME, owner_id)
                return

        # Parse Session Date
        if options["session_date"]:
            try:
                session_date = date.fromisoformat(options["session_date"])
            except ValueError:
                self.stderr.write(self.style.ERROR(f"Invalid date format: {options['session_date']}. Expected YYYY-MM-DD."))
                if not options["dry_run"] and lease_acquired:
                    DatabasePipelineLeaseManager.release_lease(PIPELINE_LEASE_NAME, owner_id)
                return
        else:
            session_date = ExchangeCalendar.get_last_trading_day()

        try:
            self._execute_session_pipeline(
                session_date,
                shadow_svc,
                options,
                run_uuid=run_uuid,
                start_time=start_time,
                owner_id=owner_id,
            )
        finally:
            if not options["dry_run"] and lease_acquired:
                DatabasePipelineLeaseManager.release_lease(PIPELINE_LEASE_NAME, owner_id)

    def _execute_session_pipeline(
        self,
        session_date: date,
        shadow_svc: ShadowEvaluationService,
        options: dict[str, Any],
        run_uuid: uuid.UUID,
        start_time: float | None = None,
        owner_id: str | None = None,
    ) -> None:
        if start_time is None:
            start_time = time.time()

        universe = (
            [s.strip().upper() for s in options["universe"].split(",") if s.strip()]
            if options.get("universe")
            else PILOT_SYMBOLS
        )
        force = options["force"]
        dry_run = options["dry_run"]
        setup_name = options["setup_name"]
        lookback_days = options["lookback_days"]
        capture_mode = options.get("capture_mode", ShadowCaptureMode.FORWARD_CAPTURED)

        self.stdout.write(f"Target Session Date: {session_date}")
        self.stdout.write(f"Universe ({len(universe)} symbols): {', '.join(universe)}")
        self.stdout.write(f"Setup: {setup_name} | Mode: {capture_mode} | Dry-run: {dry_run} | Force: {force}")

        # Create MLShadowPipelineRun tracking entry
        pipeline_run = None
        if not dry_run:
            pipeline_run = MLShadowPipelineRun.objects.create(
                run_id=run_uuid,
                session_date=session_date,
                status="RUNNING",
                health_state=PipelineHealthState.HEALTHY,
                trigger_type="MANUAL_CLI" if options.get("session_date") else "SCHEDULED_EOD",
                started_at=timezone.now(),
            )

        # Pre-Stage: Automated EOD Data Ingestion if requested
        if options.get("ingest_eod"):
            from services.market_data.eod_service import EODIngestionService

            self.stdout.write("\n[Pre-Stage] Triggering automated authentic EOD market data ingestion...")
            ingest_res = EODIngestionService.ingest_session_eod(
                session_date=session_date,
                universe=universe,
                dry_run=dry_run,
            )
            self.stdout.write(
                f"  EOD Ingestion: Status={ingest_res['status']} ({ingest_res['symbols_succeeded']}/{ingest_res['total_symbols']} symbols, "
                f"{ingest_res['candles_ingested']} candles, {ingest_res['duration_seconds']}s)"
            )
            if ingest_res.get("errors"):
                for err in ingest_res["errors"]:
                    self.stdout.write(self.style.WARNING(f"    - {err['symbol']}: {err['error']}"))

        try:
            # Stage 1: Calendar & Session Readiness Check
            self.stdout.write("\n[Stage 1/6] Validating exchange calendar and session hours...")
            readiness = shadow_svc.validate_session_readiness(session_date, required_symbols=universe, force=force)

            if not readiness["is_ready"] and not force:
                reason = readiness["reason"]
                status_code = readiness.get("status", "WAITING_FOR_DATA")
                self.stdout.write(self.style.WARNING(f"Pipeline skipped: {reason}"))
                if not dry_run:
                    if pipeline_run:
                        pipeline_run.status = status_code
                        if status_code == "SKIPPED_HOLIDAY":
                            pipeline_run.health_state = PipelineHealthState.HEALTHY
                        elif status_code == "WAITING_FOR_DATA":
                            pipeline_run.health_state = PipelineHealthState.WAITING_FOR_DATA
                        elif status_code == "DEGRADED":
                            pipeline_run.health_state = PipelineHealthState.DEGRADED
                        else:
                            pipeline_run.health_state = PipelineHealthState.FAILED

                        pipeline_run.error_details = reason
                        pipeline_run.completed_at = timezone.now()
                        pipeline_run.duration_seconds = round(time.time() - start_time, 2)
                        pipeline_run.save()

                    shadow_svc.record_pipeline_event(
                        event_type="SHADOW_PIPELINE_SKIPPED" if status_code == "SKIPPED_HOLIDAY" else "SHADOW_INSUFFICIENT_DATA",
                        severity="LOW" if status_code == "SKIPPED_HOLIDAY" else "HIGH",
                        details={
                            "session_date": session_date.isoformat(),
                            "status": status_code,
                            "reason": reason,
                            "missing_symbols": readiness.get("missing_symbols", []),
                            "candle_count": readiness.get("candle_count", 0),
                        },
                    )
                return

            self.stdout.write(self.style.SUCCESS(f"  Session validated: {readiness['reason']}"))
            if readiness.get("candle_count"):
                self.stdout.write(f"  Available 1d candles: {readiness['candle_count']} (Benchmark ^NSEI: {readiness['benchmark_available']})")

            # Stage 2: Load Historical Price Data for Feature Transformation
            if owner_id and not dry_run:
                DatabasePipelineLeaseManager.renew_heartbeat(PIPELINE_LEASE_NAME, owner_id)
            self.stdout.write("\n[Stage 2/6] Ingesting point-in-time canonical market data...")
            start_date = session_date - timedelta(days=lookback_days)
            builder = DatasetBuilder(
                start_date=start_date,
                end_date=session_date,
                universe=universe,
                require_authentic_data=True,
                deduplicate_dual_listings=True,
            )
            df_canonical, metadata = builder.build_canonical_dataframe()

            if df_canonical.empty:
                msg = f"No canonical price records found between {start_date} and {session_date}."
                self.stderr.write(self.style.ERROR(f"  {msg}"))
                if not dry_run:
                    if pipeline_run:
                        pipeline_run.status = "FAILED"
                        pipeline_run.health_state = PipelineHealthState.DEGRADED
                        pipeline_run.error_details = msg
                        pipeline_run.completed_at = timezone.now()
                        pipeline_run.duration_seconds = round(time.time() - start_time, 2)
                        pipeline_run.save()

                    shadow_svc.record_pipeline_event(
                        event_type="SHADOW_INSUFFICIENT_DATA",
                        severity="HIGH",
                        details={"session_date": session_date.isoformat(), "error": msg},
                    )
                return

            self.stdout.write(f"  Loaded {len(df_canonical):,} price rows across {df_canonical['symbol'].nunique()} symbols.")

            # Stage 3: Feature Engineering & Heuristic Candidate Extraction
            self.stdout.write("\n[Stage 3/6] Computing feature pipeline and identifying setup candidates...")
            fp = FeaturePipeline()
            df_feat = fp.transform_universe_canonical(df_canonical)

            sdate_str = session_date.isoformat()
            df_session = df_feat[df_feat["session_date"] == sdate_str].copy()
            self.stdout.write(f"  Features calculated for {len(df_session)} symbols on session {sdate_str}.")

            if df_session.empty:
                msg = f"Zero features calculated for target session {sdate_str}. Missing target-session candles in canonical dataset."
                self.stderr.write(self.style.ERROR(f"  {msg}"))
                if not dry_run:
                    if pipeline_run:
                        pipeline_run.status = "FAILED"
                        pipeline_run.health_state = PipelineHealthState.DEGRADED
                        pipeline_run.error_details = msg
                        pipeline_run.completed_at = timezone.now()
                        pipeline_run.duration_seconds = round(time.time() - start_time, 2)
                        pipeline_run.save()

                    shadow_svc.record_pipeline_event(
                        event_type="SHADOW_INSUFFICIENT_DATA",
                        severity="HIGH",
                        details={"session_date": sdate_str, "error": msg},
                    )
                return

            if len(df_session) < len(universe) * 0.5:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Warning: Partial feature coverage ({len(df_session)}/{len(universe)} symbols). Marking DEGRADED."
                    )
                )
                if pipeline_run:
                    pipeline_run.health_state = PipelineHealthState.DEGRADED

            df_cand = df_session[
                (df_session["price_to_sma200"] > 0.0)
                & (df_session["rsi_14"] >= 35.0)
                & (df_session["rsi_14"] <= 50.0)
                & (df_session["stoch_rsi_k"] < 25.0)
            ].copy()

            self.stdout.write(f"  Identified {len(df_cand)} candidate setup(s) meeting {setup_name} rules.")

            # Stage 4: Point-in-Time Risk Veto & Decision Persistence
            self.stdout.write("\n[Stage 4/6] Evaluating explainable risk-veto classifications...")
            records = []
            if not df_cand.empty:
                for _, r in df_cand.iterrows():
                    assess = shadow_svc.risk_engine.assess_setup(r)
                    status_str = "VETOED" if assess.is_vetoed else "ACCEPTED"
                    self.stdout.write(
                        f"    - {r['symbol']}: Regime={assess.regime.value}, Risk={assess.risk_level.value} "
                        f"(Score: {assess.risk_score}) -> {status_str}"
                    )
                    if assess.veto_reasons:
                        self.stdout.write(f"      Reasons: {', '.join(assess.veto_reasons)}")

                if not dry_run:
                    candle_ts = HistoricalCandle.objects.filter(
                        timestamp__date=session_date,
                        interval="1d",
                    ).aggregate(models.Max("retrieved_at"))["retrieved_at__max"]

                    records = shadow_svc.record_session_candidates(
                        df_cand,
                        setup_name=setup_name,
                        source_provider="AUTHENTIC_EOD",
                        actual_data_as_of=candle_ts,
                        capture_mode=capture_mode,
                        processing_run_id=run_uuid,
                        force=force,
                    )
                    self.stdout.write(self.style.SUCCESS(f"  Persisted {len(records)} immutable shadow records with SHA-256 checksums ({capture_mode})."))
                else:
                    self.stdout.write(self.style.NOTICE(f"  [Dry-run] Would persist {len(df_cand)} shadow evaluation records."))
            else:
                self.stdout.write("  No setups triggered on this session. Zero false positives recorded.")

            # Stage 5: Independent Per-Horizon Forward Outcome Maturation
            if owner_id and not dry_run:
                DatabasePipelineLeaseManager.renew_heartbeat(PIPELINE_LEASE_NAME, owner_id)
            self.stdout.write("\n[Stage 5/6] Matures independent forward horizons (5d, 10d, 20d)...")
            matured_count = 0
            if not dry_run:
                matured_count = shadow_svc.mature_pending_evaluations(df_canonical, as_of_session=session_date)
                stats = shadow_svc.last_maturation_stats
                self.stdout.write(self.style.SUCCESS(
                    f"  Matured: 5d={stats['matured_5d']}, 10d={stats['matured_10d']}, 20d={stats['matured_20d']} "
                    f"(Total Updated: {matured_count})"
                ))
            else:
                self.stdout.write(self.style.NOTICE("  [Dry-run] Forward maturation skipped."))

            # Stage 6: Operational Audit Event Logging
            elapsed = round(time.time() - start_time, 2)
            summary = shadow_svc.compute_shadow_summary(forward_only=False)
            self.stdout.write("\n[Stage 6/6] Logging operational monitoring event and telemetry...")

            if not dry_run:
                active_model = MLModelRecord.objects.filter(algorithm="LIGHTGBM").first()
                shadow_svc.record_pipeline_event(
                    event_type="SHADOW_PIPELINE_RUN",
                    severity="LOW",
                    details={
                        "run_id": str(run_uuid),
                        "session_date": sdate_str,
                        "universe_size": len(universe),
                        "candidates_count": len(df_cand),
                        "records_persisted": len(records),
                        "matured_5d": shadow_svc.last_maturation_stats["matured_5d"],
                        "matured_10d": shadow_svc.last_maturation_stats["matured_10d"],
                        "matured_20d": shadow_svc.last_maturation_stats["matured_20d"],
                        "total_matured_updated": matured_count,
                        "capture_mode": capture_mode,
                        "elapsed_seconds": elapsed,
                        "status": "SUCCESS",
                    },
                    model_record=active_model,
                )

                if pipeline_run:
                    if pipeline_run.health_state == PipelineHealthState.DEGRADED:
                        pipeline_run.status = "DEGRADED"
                    else:
                        pipeline_run.status = "SUCCESS"
                        pipeline_run.health_state = PipelineHealthState.HEALTHY
                    pipeline_run.completed_at = timezone.now()
                    pipeline_run.duration_seconds = elapsed
                    pipeline_run.records_created = len(records)
                    pipeline_run.outcomes_matured_5d = shadow_svc.last_maturation_stats["matured_5d"]
                    pipeline_run.outcomes_matured_10d = shadow_svc.last_maturation_stats["matured_10d"]
                    pipeline_run.outcomes_matured_20d = shadow_svc.last_maturation_stats["matured_20d"]
                    pipeline_run.save()

            self.stdout.write("\n" + "=" * 60)
            self.stdout.write(self.style.SUCCESS(f"Pipeline finished successfully in {elapsed}s."))
            self.stdout.write(f"Total Shadow Records: {summary['total_evaluations']} (Matured 20d: {summary['matured_evaluations']}, Pending: {summary['pending_evaluations']})")
            self.stdout.write(f"Matured Horizons: 5d={summary.get('matured_5d_count', 0)}, 10d={summary.get('matured_10d_count', 0)}, 20d={summary.get('matured_20d_count', 0)}")
            self.stdout.write(f"Accepted: {summary['accepted_count']} (Mean 20d: {summary['accepted_mean_return_20d_pct']}%)")
            self.stdout.write(f"Vetoed: {summary['vetoed_count']} (Mean 20d: {summary['vetoed_mean_return_20d_pct']}%)")
            self.stdout.write(f"Alpha Spread: {summary['veto_alpha_spread_pct']}%")
            self.stdout.write("=" * 60)

        except Exception as exc:
            elapsed = round(time.time() - start_time, 2)
            self.stderr.write(self.style.ERROR(f"Pipeline failed with exception: {exc}"))
            if not dry_run and pipeline_run:
                pipeline_run.status = "FAILED"
                pipeline_run.health_state = PipelineHealthState.FAILED
                pipeline_run.error_details = str(exc)
                pipeline_run.completed_at = timezone.now()
                pipeline_run.duration_seconds = elapsed
                pipeline_run.save()

                shadow_svc.record_pipeline_event(
                    event_type="SHADOW_PIPELINE_ERROR",
                    severity="CRITICAL",
                    details={
                        "run_id": str(run_uuid),
                        "session_date": sdate_str if "sdate_str" in locals() else str(session_date),
                        "error": str(exc),
                        "elapsed_seconds": elapsed,
                    },
                )
            raise
