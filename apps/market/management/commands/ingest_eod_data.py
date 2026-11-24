"""
Django Management Command: ingest_eod_data
Automated EOD Market Data Ingestion for KuberLens Pilot Equities and Benchmark.
Complies with AIML Architecture v2.1 Section 18 Master Specification.
"""
from datetime import date
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from services.market_data.eod_service import PILOT_SYMBOLS, EODIngestionService


class Command(BaseCommand):
    help = "Ingests authentic end-of-day candles for the pilot equities universe and benchmark index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-date",
            type=str,
            help="Trading session date (YYYY-MM-DD). Defaults to latest eligible trading session.",
        )
        parser.add_argument(
            "--universe",
            type=str,
            help="Comma-separated list of symbols (default: 11 pilot equities).",
        )
        parser.add_argument(
            "--provider",
            type=str,
            default="YAHOO",
            help="Primary data provider code (default: YAHOO).",
        )
        parser.add_argument(
            "--fallback-provider",
            type=str,
            default="JUGAAD",
            help="Fallback data provider code (default: JUGAAD).",
        )
        parser.add_argument(
            "--max-retries",
            type=int,
            default=3,
            help="Maximum retry attempts per instrument (default: 3).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Perform provider queries and validation without writing to database.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        session_date_str = options.get("session_date")
        if session_date_str:
            try:
                session_date = date.fromisoformat(session_date_str)
            except ValueError:
                raise CommandError(f"Invalid date format: {session_date_str}. Expected YYYY-MM-DD.") from None
        else:
            session_date = None

        universe_str = options.get("universe")
        universe = (
            [s.strip().upper() for s in universe_str.split(",") if s.strip()]
            if universe_str
            else PILOT_SYMBOLS
        )

        dry_run = options.get("dry_run", False)
        primary_provider = options.get("provider", "YAHOO")
        fallback_provider = options.get("fallback_provider", "JUGAAD")
        max_retries = options.get("max_retries", 3)

        self.stdout.write(self.style.MIGRATE_HEADING("=== KuberLens: Automated EOD Market Data Ingestion ==="))
        if session_date:
            self.stdout.write(f"Target Session Date: {session_date}")
        self.stdout.write(f"Universe ({len(universe)} equities + benchmark): {', '.join(universe)}")
        self.stdout.write(f"Primary Provider: {primary_provider} | Fallback: {fallback_provider} | Dry-run: {dry_run}")

        result = EODIngestionService.ingest_session_eod(
            session_date=session_date,
            universe=universe,
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            max_retries=max_retries,
            dry_run=dry_run,
        )

        status = result["status"]
        s_date = result["session_date"]
        duration = result["duration_seconds"]

        if status == "SKIPPED_HOLIDAY":
            self.stdout.write(
                self.style.WARNING(
                    f"Session {s_date} is not an active exchange trading day ({result.get('holiday_reason')}). Skipped."
                )
            )
            return

        if status == "SUCCESS":
            self.stdout.write(
                self.style.SUCCESS(
                    f"SUCCESS: Ingested {result['candles_ingested']} candles for {result['symbols_succeeded']}/{result['total_symbols']} "
                    f"instruments in {duration}s."
                )
            )
            return

        if status == "DEGRADED":
            self.stdout.write(
                self.style.WARNING(
                    f"DEGRADED: Partial ingestion ({result['symbols_succeeded']}/{result['total_symbols']} succeeded). "
                    f"Missing symbols: {', '.join(result['missing_symbols'])}."
                )
            )
            for err in result.get("errors", []):
                self.stderr.write(f"  - {err['symbol']}: {err['error']}")
            raise CommandError(f"EOD Ingestion completed with DEGRADED status for session {s_date}.")

        if status == "WAITING_FOR_DATA":
            self.stdout.write(
                self.style.NOTICE(
                    f"WAITING_FOR_DATA: Session {s_date} market data not yet published or market still open. ({result.get('reason')})"
                )
            )
            raise CommandError(f"Market data not yet available for session {s_date}.")

        if status == "FAILED":
            self.stderr.write(
                self.style.ERROR(
                    f"FAILED: EOD Ingestion failed for session {s_date}. {result.get('reason')}"
                )
            )
            for err in result.get("errors", []):
                self.stderr.write(f"  - {err['symbol']}: {err['error']}")
            raise CommandError(f"EOD Ingestion failed for session {s_date}.")
