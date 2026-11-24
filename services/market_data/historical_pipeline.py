"""
Scalable Historical Market Data Ingestion Pipeline for KuberLens.
Complies with AIML Architecture v2.1, Section 18 Master Specification, and Phase 3.2 Requirements.
Supports:
- NSE equities and BSE equities
- NIFTY 50 benchmark index history (^NSEI)
- Incremental ingestion with resumable checkpoints
- Idempotent upserts of HistoricalCandle records
- Strict rate-limit compliance, pacing and failure retry
- Provenance and data-quality audit logging
- Validation against ExchangeCalendar trading sessions
- Never overwrites verified authentic market data with synthetic fixtures
"""
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import DataQualityIssue, HistoricalCandle
from integrations.market_data.registry import ProviderRegistry
from services.calendar.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)

AUTHENTIC_PROVIDERS = {"EXCHANGE", "NSE_BHAVCOPY", "BSE_BHAVCOPY", "JUGAAD", "YAHOO"}
PROVIDER_PRECEDENCE = {
    "EXCHANGE": 100,
    "NSE_BHAVCOPY": 90,
    "BSE_BHAVCOPY": 90,
    "JUGAAD": 80,
    "YAHOO": 70,
    "SEEDED": 10,
    "SYNTHETIC": 0,
    "UNKNOWN": 0,
}


@dataclass
class IngestionCheckpoint:
    listing_id: str
    symbol: str
    exchange: str
    last_ingested_date: date | None
    total_candles_ingested: int
    status: str  # SUCCESS, PARTIAL, FAILED, RATE_LIMITED
    error_message: str | None = None


class HistoricalDataIngestionPipeline:
    """
    Production-grade historical candle ingestion pipeline.
    Orchestrates batch fetches from registered authentic providers (Jugaad, Yahoo),
    validates data quality and calendar trading dates, performs atomic upserts,
    and updates resumable checkpoints.
    Supports backfill mode and missing trading session gap repair.
    """

    def __init__(
        self,
        provider_code: str = "YAHOO",
        rate_limit_delay_seconds: float = 0.5,
        max_retries: int = 3,
        batch_size: int = 50,
        verify_against_calendar: bool = True,
        backfill_mode: bool = False,
    ):
        self.provider_code = provider_code.upper()
        self.rate_limit_delay_seconds = rate_limit_delay_seconds
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.verify_against_calendar = verify_against_calendar
        self.backfill_mode = backfill_mode

    def get_provider(self):
        """Retrieves provider instance from registry."""
        return ProviderRegistry.get(self.provider_code)

    def register_or_get_benchmark_listing(self) -> ExchangeListing:
        """
        Ensures the canonical NIFTY 50 (^NSEI) benchmark instrument and listing exist in DB.
        NIFTY 50 is treated as a benchmark index with an internal identifier, never as an equity.
        """
        nse, _ = Exchange.objects.get_or_create(
            code="NSE",
            defaults={"name": "National Stock Exchange of India"},
        )
        inst = Instrument.objects.filter(isin__in=["IN_INDEX_NIFTY50", "IN999NIFTY50"]).first()
        if not inst:
            inst = Instrument.objects.create(
                isin="IN_INDEX_NIFTY50",
                display_name="NIFTY 50",
                legal_name="NIFTY 50 Benchmark Index",
                sector="INDEX",
                industry="BENCHMARK",
                market_cap_category="INDEX",
                is_active=True,
            )
        listing, _ = ExchangeListing.objects.get_or_create(
            exchange=nse,
            symbol="^NSEI",
            defaults={
                "instrument": inst,
                "trading_symbol": "NIFTY 50",
                "series_or_group": "INDEX",
                "is_primary": True,
                "is_tradeable": False,
            },
        )
        return listing

    def detect_missing_session_gaps(
        self,
        listing: ExchangeListing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
        require_authentic: bool = True,
    ) -> list[date]:
        """
        Detects missing trading session dates between start_date and end_date for a given listing.
        Checks against ExchangeCalendar trading sessions.
        """
        expected_days = ExchangeCalendar.get_trading_days(start_date, end_date)
        qs = HistoricalCandle.objects.filter(
            listing=listing,
            interval=interval,
            timestamp__gte=timezone.datetime.combine(start_date, timezone.datetime.min.time(), tzinfo=timezone.get_current_timezone()),
            timestamp__lte=timezone.datetime.combine(end_date, timezone.datetime.max.time(), tzinfo=timezone.get_current_timezone()),
        )
        if require_authentic:
            qs = qs.filter(source_provider__in=AUTHENTIC_PROVIDERS)

        existing_dates = {ts.date() for ts in qs.values_list("timestamp", flat=True)}
        missing_gaps = [d for d in expected_days if d not in existing_dates]
        return sorted(missing_gaps)

    def repair_session_gaps(
        self,
        listing: ExchangeListing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
    ) -> dict[str, Any]:
        """
        Detects and attempts targeted backfill repair for missing trading sessions.
        """
        gaps = self.detect_missing_session_gaps(listing, start_date, end_date, interval, require_authentic=True)
        if not gaps:
            return {
                "listing": listing.symbol,
                "gaps_detected": 0,
                "gaps_repaired": 0,
                "remaining_gaps": 0,
                "status": "NO_GAPS",
            }

        # Backfill over the range spanning the gaps
        chk = self.ingest_listing_history(
            listing=listing,
            start_date=min(gaps),
            end_date=max(gaps),
            interval=interval,
            backfill_mode=True,
        )

        remaining_gaps = self.detect_missing_session_gaps(listing, start_date, end_date, interval, require_authentic=True)
        repaired_count = len(gaps) - len(remaining_gaps)

        return {
            "listing": listing.symbol,
            "gaps_detected": len(gaps),
            "gaps_repaired": repaired_count,
            "remaining_gaps": len(remaining_gaps),
            "status": "REPAIRED" if not remaining_gaps else "PARTIAL",
            "checkpoint_status": chk.status,
        }

    def ingest_listing_history(
        self,
        listing: ExchangeListing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
        backfill_mode: bool | None = None,
    ) -> IngestionCheckpoint:
        """
        Ingests historical candles for a single listing with rate-limiting,
        retries, calendar verification, source precedence, and idempotent database upsert.
        """
        is_backfill = self.backfill_mode if backfill_mode is None else backfill_mode
        provider = self.get_provider()
        symbol = listing.symbol
        exchange_code = listing.exchange.code

        effective_start = start_date

        if not is_backfill:
            # Check existing latest authentic candle to support resumable incremental ingestion
            latest_existing = HistoricalCandle.objects.filter(
                listing=listing,
                interval=interval,
                source_provider=self.provider_code,
            ).order_by("-timestamp").first()

            if latest_existing:
                next_needed = latest_existing.timestamp.date() + timedelta(days=1)
                if next_needed > effective_start:
                    effective_start = next_needed

            if effective_start > end_date:
                logger.info("[%s] Already up to date through %s.", symbol, end_date)
                return IngestionCheckpoint(
                    listing_id=str(listing.id),
                    symbol=symbol,
                    exchange=exchange_code,
                    last_ingested_date=latest_existing.timestamp.date() if latest_existing else None,
                    total_candles_ingested=0,
                    status="SUCCESS",
                )

        candles_raw = []
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.rate_limit_delay_seconds)
                candles_raw = provider.get_historical_candles(
                    listing=listing,
                    start_date=effective_start,
                    end_date=end_date,
                    interval=interval,
                )
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[%s] Attempt %d/%d failed: %s",
                    symbol, attempt, self.max_retries, exc,
                )
                time.sleep(self.rate_limit_delay_seconds * (2 ** attempt))

        if not candles_raw:
            err_msg = str(last_error) if last_error else "Zero candles returned by provider."
            # Log DataQualityIssue
            DataQualityIssue.objects.create(
                listing=listing,
                issue_type="PROVIDER_DISCREPANCY",
                severity="MEDIUM",
                details={
                    "error": err_msg,
                    "provider": self.provider_code,
                    "start_date": effective_start.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
            return IngestionCheckpoint(
                listing_id=str(listing.id),
                symbol=symbol,
                exchange=exchange_code,
                last_ingested_date=None,
                total_candles_ingested=0,
                status="FAILED",
                error_message=err_msg,
            )

        # Filter against ExchangeCalendar if requested
        valid_candles = []
        for c in candles_raw:
            cdate = c.timestamp.date()
            if self.verify_against_calendar and not ExchangeCalendar.is_trading_day(cdate):
                logger.debug("[%s] Skipping candle on non-trading session: %s", symbol, cdate)
                continue
            valid_candles.append(c)

        # Idempotent upsert in atomic database transaction with source precedence enforcement
        ingested_count = 0
        latest_date = None
        incoming_priority = PROVIDER_PRECEDENCE.get(self.provider_code, 50)

        with transaction.atomic():
            for c in valid_candles:
                cdate = c.timestamp.date()
                existing = HistoricalCandle.objects.select_for_update().filter(
                    listing=listing,
                    timestamp=c.timestamp,
                    interval=interval,
                ).first()

                if existing:
                    existing_priority = PROVIDER_PRECEDENCE.get(existing.source_provider, 0)
                    if incoming_priority < existing_priority:
                        # Higher precedence authentic data exists; do NOT overwrite
                        logger.debug(
                            "[%s] Preserving higher-precedence candle on %s (%s >= %s)",
                            symbol, cdate, existing.source_provider, self.provider_code,
                        )
                        continue

                    # Update existing record (e.g. authentic provider replacing synthetic/seeded fixture)
                    existing.open = c.open
                    existing.high = c.high
                    existing.low = c.low
                    existing.close = c.close
                    existing.volume = c.volume
                    existing.adjusted_close = c.adjusted_close
                    existing.source_provider = self.provider_code
                    existing.save()
                else:
                    HistoricalCandle.objects.create(
                        listing=listing,
                        timestamp=c.timestamp,
                        interval=interval,
                        open=c.open,
                        high=c.high,
                        low=c.low,
                        close=c.close,
                        volume=c.volume,
                        adjusted_close=c.adjusted_close,
                        source_provider=self.provider_code,
                    )

                ingested_count += 1
                if latest_date is None or cdate > latest_date:
                    latest_date = cdate

        logger.info(
            "[%s] Successfully ingested %d authentic candles from %s.",
            symbol, ingested_count, self.provider_code,
        )

        return IngestionCheckpoint(
            listing_id=str(listing.id),
            symbol=symbol,
            exchange=exchange_code,
            last_ingested_date=latest_date,
            total_candles_ingested=ingested_count,
            status="SUCCESS",
        )

    def ingest_universe(
        self,
        listings: list[ExchangeListing],
        start_date: date,
        end_date: date,
        interval: str = "1d",
        backfill_mode: bool | None = None,
    ) -> dict[str, Any]:
        """
        Executes bounded batch historical ingestion across a list of listings.
        """
        results: list[IngestionCheckpoint] = []
        total = len(listings)
        success_count = 0
        failed_count = 0
        total_candles = 0

        for i, lst in enumerate(listings, 1):
            chk = self.ingest_listing_history(lst, start_date, end_date, interval, backfill_mode=backfill_mode)
            results.append(chk)
            if chk.status == "SUCCESS":
                success_count += 1
                total_candles += chk.total_candles_ingested
            else:
                failed_count += 1

            if i % self.batch_size == 0 or i == total:
                logger.info(
                    "Ingestion progress: %d/%d processed (%d success, %d failed, %d candles).",
                    i, total, success_count, failed_count, total_candles,
                )

        return {
            "total_processed": total,
            "success_count": success_count,
            "failed_count": failed_count,
            "total_candles_ingested": total_candles,
            "provider": self.provider_code,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "checkpoints": [
                {
                    "symbol": c.symbol,
                    "exchange": c.exchange,
                    "status": c.status,
                    "candles": c.total_candles_ingested,
                    "latest_date": c.last_ingested_date.isoformat() if c.last_ingested_date else None,
                    "error": c.error_message,
                }
                for c in results
            ],
        }
