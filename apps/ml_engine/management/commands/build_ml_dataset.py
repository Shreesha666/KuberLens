"""
Management command to build point-in-time ML historical dataset snapshots.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1.
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
        "adjustments, data quality validation, and SHA-256 canonical content hashing."
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
            help="Exchange code (NSE or BSE). Defaults to NSE.",
        )
        parser.add_argument(
            "--universe",
            type=str,
            default="nifty250",
            help="Stock universe: 'nifty250', 'all', or comma-separated symbols. Defaults to 'nifty250'.",
        )
        parser.add_argument(
            "--snapshot-name",
            type=str,
            default="nifty250_historical_dataset",
            help="Descriptive name for the dataset snapshot.",
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
        self.stdout.write(f"  Mode:           {'DRY RUN (In-Memory Audit)' if dry_run else 'PERSIST (Save to Disk & DB)'}\n")

        builder = DatasetBuilder(
            start_date=start_date,
            end_date=end_date,
            exchange_code=exchange,
            universe=universe,
            as_of_date=end_date,
        )

        expected_sessions = builder.get_expected_trading_sessions()
        self.stdout.write(f"Identified {len(expected_sessions)} expected exchange trading sessions.")

        listings = builder.resolve_universe()
        self.stdout.write(f"Resolved eligible universe: {len(listings)} listings.")

        if not listings:
            raise CommandError(f"No listings found for universe '{universe}' on exchange '{exchange}'.")

        self.stdout.write("Extracting candles, auditing data quality, and applying point-in-time corporate adjustments...")
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

        if metadata["excluded_listings"]:
            self.stdout.write(self.style.WARNING(f"\n  Excluded Listings ({len(metadata['excluded_listings'])}):"))
            for sym, reason in list(metadata["excluded_listings"].items())[:10]:
                self.stdout.write(f"    - {sym}: {reason}")
            if len(metadata["excluded_listings"]) > 10:
                self.stdout.write(f"    ... and {len(metadata['excluded_listings']) - 10} more.")

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
