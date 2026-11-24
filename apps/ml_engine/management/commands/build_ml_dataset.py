"""
Management command to build point-in-time ML historical dataset snapshots.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1 (Phase 2 & 2.1).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from services.calendar.exchange_calendar import ExchangeCalendar
from services.ml.dataset_builder import DatasetBuilder


class Command(BaseCommand):
    help = (
        "Builds a point-in-time historical dataset snapshot with verified corporate-action "
        "adjustments, multi-exchange universe resolution, dual-listing deduplication, "
        "ML eligibility classification, and SHA-256 canonical content hashing."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--start-date",
            type=str,
            default=None,
            help="Start date for historical candles (YYYY-MM-DD). Defaults to 1 year ago.",
        )
        parser.add_argument(
            "--end-date",
            type=str,
            default=None,
            help="End date for historical candles (YYYY-MM-DD). Defaults to most recent trading day.",
        )
        parser.add_argument(
            "--exchange",
            type=str,
            default="NSE",
            help="Exchange code (NSE, BSE, or ALL). Defaults to NSE.",
        )
        parser.add_argument(
            "--universe",
            type=str,
            default="NIFTY_250",
            help="Stock universe: 'ALL_NSE', 'ALL_BSE', 'ALL_NSE_BSE', 'NIFTY_50', 'NIFTY_100', 'NIFTY_250', 'PORTFOLIO_HOLDINGS', or comma-separated symbols. Defaults to 'NIFTY_250'.",
        )
        parser.add_argument(
            "--snapshot-name",
            type=str,
            default="historical_dataset",
            help="Descriptive name for the dataset snapshot.",
        )
        parser.add_argument(
            "--deduplicate-dual-listings",
            action="store_true",
            default=True,
            help="Deduplicate dual-listed securities across NSE and BSE by ISIN. Defaults to True.",
        )
        parser.add_argument(
            "--primary-policy",
            type=str,
            default="PRIMARY_FLAG_THEN_LIQUIDITY",
            choices=["PRIMARY_FLAG_THEN_LIQUIDITY", "NSE_PRIORITY", "BSE_PRIORITY"],
            help="Policy for selecting primary listing when deduplicating dual-listed securities.",
        )
        parser.add_argument(
            "--min-sessions",
            type=int,
            default=200,
            help="Minimum session count required for ML_ELIGIBLE classification. Defaults to 200.",
        )
        parser.add_argument(
            "--min-volume",
            type=float,
            default=5000.0,
            help="Minimum median daily volume required for ML_ELIGIBLE classification. Defaults to 5,000.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=50,
            help="Batch size for chunked streaming extraction. Defaults to 50 listings.",
        )
        parser.add_argument(
            "--audit-only",
            action="store_true",
            help="Perform comprehensive historical data readiness and eligibility audit without generating dataset files.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Execute full extraction and quality audit without writing to disk or database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        exchange = options["exchange"].upper()
        universe = options["universe"]
        snapshot_name = options["snapshot_name"]
        dedup_dual = options["deduplicate_dual_listings"]
        primary_policy = options["primary_policy"]
        min_sessions = options["min_sessions"]
        min_volume = options["min_volume"]
        chunk_size = options["chunk_size"]
        audit_only = options["audit_only"]
        dry_run = options["dry_run"]

        # Parse dates
        end_date_str = options["end_date"]
        if end_date_str:
            try:
                end_date = date.fromisoformat(end_date_str)
            except ValueError as err:
                raise CommandError(f"Invalid --end-date format: '{end_date_str}'. Expected YYYY-MM-DD.") from err
        else:
            end_date = ExchangeCalendar.get_last_trading_day()

        start_date_str = options["start_date"]
        if start_date_str:
            try:
                start_date = date.fromisoformat(start_date_str)
            except ValueError as err:
                raise CommandError(f"Invalid --start-date format: '{start_date_str}'. Expected YYYY-MM-DD.") from err
        else:
            start_date = end_date - timedelta(days=365)

        if start_date >= end_date:
            raise CommandError(f"--start-date ({start_date}) must be before --end-date ({end_date}).")

        self.stdout.write(self.style.MIGRATE_HEADING("\n=== KuberLens AI/ML Dataset Snapshot Builder ==="))
        self.stdout.write(f"  Exchange:       {exchange}")
        self.stdout.write(f"  Universe:       {universe}")
        self.stdout.write(f"  Date Range:     {start_date} to {end_date}")
        self.stdout.write(f"  Snapshot Name:  {snapshot_name}")
        self.stdout.write(f"  Dual Dedup:     {dedup_dual} (Policy: {primary_policy})")
        self.stdout.write(f"  Chunk Size:     {chunk_size}")
        self.stdout.write(f"  Mode:           {'AUDIT ONLY' if audit_only else ('DRY RUN' if dry_run else 'PERSIST')}\n")

        builder = DatasetBuilder(
            start_date=start_date,
            end_date=end_date,
            exchange_code=exchange,
            universe=universe,
            as_of_date=end_date,
            deduplicate_dual_listings=dedup_dual,
            primary_policy=primary_policy,
            chunk_size=chunk_size,
            min_sessions=min_sessions,
            min_median_volume=min_volume,
        )

        expected_sessions = builder.get_expected_trading_sessions()
        self.stdout.write(f"Identified {len(expected_sessions)} expected exchange trading sessions.")

        listings, universe_meta = builder.resolve_universe()
        self.stdout.write(f"Resolved Universe: {universe_meta['description']}")
        self.stdout.write(f"  Raw Candidates: {universe_meta['raw_candidates_count']} listings")
        self.stdout.write(f"  Deduplicated:   {universe_meta['deduplicated_duplicates_count']} duplicate dual listings")
        self.stdout.write(f"  Final Target:   {len(listings)} listings\n")

        if not listings:
            raise CommandError(f"No listings found for universe '{universe}' on exchange '{exchange}'.")

        if audit_only:
            self.stdout.write("Running comprehensive historical data readiness and eligibility audit...")
            audit_report = builder.audit_universe_readiness()

            self.stdout.write(self.style.SUCCESS("\n--- Historical Data Readiness & Coverage Audit ---"))
            self.stdout.write(f"  Total Listings Audited:          {audit_report['total_listings_audited']}")
            self.stdout.write(f"  Distinct Securities (ISINs):     {audit_report['distinct_securities_count']}")
            self.stdout.write(f"  Expected Trading Sessions:       {audit_report['expected_trading_sessions_count']}")
            self.stdout.write(f"  Earliest Available Session:      {audit_report['earliest_global_session']}")
            self.stdout.write(f"  Latest Available Session:        {audit_report['latest_global_session']}")
            self.stdout.write(f"  Total Clean Samples:             {audit_report['total_clean_samples']:,}")
            self.stdout.write(f"  Quarantined Invalid Candles:     {audit_report['total_quarantined_candles']}")
            self.stdout.write(f"  Average Session Coverage:        {audit_report['average_coverage_pct']}%")

            self.stdout.write(self.style.MIGRATE_LABEL("\nHistorical Depth Distribution:"))
            for tier, count in audit_report["coverage_distribution"].items():
                self.stdout.write(f"    - {tier}: {count} listings")

            self.stdout.write(self.style.MIGRATE_LABEL("\nML Eligibility Classification Breakdown:"))
            for status, count in audit_report["status_counts"].items():
                self.stdout.write(f"    - {status}: {count} listings")

            self.stdout.write(self.style.MIGRATE_LABEL("\nMissing Sessions Root Cause Analysis:"))
            for reason, count in audit_report["missing_session_reasons"].items():
                self.stdout.write(f"    - {reason}: {count} total session gaps")

            self.stdout.write(self.style.MIGRATE_LABEL("\nReadiness Gates:"))
            self.stdout.write(f"    - Ready for Phase 3 (Feature Engineering): {'YES' if audit_report['ready_for_phase_3'] else 'NO'}")
            self.stdout.write(f"    - Ready for Phase 4 (Model Walk-Forward Training): {'YES' if audit_report['ready_for_phase_4'] else 'NO'}")
            if not audit_report["ready_for_phase_4"]:
                self.stdout.write(self.style.WARNING(f"      Reason: {audit_report['phase_4_readiness_reason']}"))
            return

        self.stdout.write("Extracting candles in bounded chunks, validating quality, and applying corporate adjustments...")
        canonical_df, metadata = builder.build_canonical_dataframe()

        self.stdout.write(self.style.SUCCESS("\n--- Dataset Build & Quality Audit Results ---"))
        self.stdout.write(f"  Total Clean Samples:             {metadata['total_samples']:,} rows")
        self.stdout.write(f"  Listings with Sufficient Data:   {metadata['active_listings_with_data']} / {metadata['universe_size']}")
        self.stdout.write(f"  Average Session Coverage:        {metadata['average_coverage_pct']}%")
        self.stdout.write(f"  Quarantined Invalid Candles:     {metadata['total_quarantined_candles']}")
        self.stdout.write(f"  Suspicious Price Jumps (>50%):   {metadata['total_suspicious_jumps']}")
        self.stdout.write(f"  Corporate Actions Applied:       {metadata['total_corporate_actions_applied']}")
        self.stdout.write(f"  Universe Hash (SHA-256):         {metadata['universe_hash'][:16]}...")
        self.stdout.write(f"  Content Hash (SHA-256):          {metadata['content_hash']}")

        snapshot = builder.save_snapshot(
            canonical_df=canonical_df,
            snapshot_name=snapshot_name,
            summary_metadata=metadata,
            dry_run=dry_run,
        )

        if dry_run:
            self.stdout.write(self.style.NOTICE(f"\n[DRY RUN] In-memory snapshot constructed ({snapshot.version}). No changes committed to disk or database."))
        else:
            self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Dataset snapshot persisted!"))
            self.stdout.write(f"  Snapshot ID:     {snapshot.id}")
            self.stdout.write(f"  Version:         {snapshot.version}")
            self.stdout.write(f"  Quality Status:  {snapshot.quality_status}")
            self.stdout.write(f"  Storage Path:    {snapshot.storage_path}\n")
