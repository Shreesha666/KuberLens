"""
Automated Daily EOD Market Data Ingestion Service for KuberLens.
Complies with AIML Architecture v2.1, Section 18 Master Specification.

Responsibilities:
1. Orchestrates daily EOD candle ingestion for the 11 pilot equities and ^NSEI benchmark.
2. Enforces exchange trading calendar and post-market settlement hours (19:15 IST).
3. Bounded retries with exponential backoff for provider network/DNS failures.
4. Idempotent database upserts with source precedence and genuine retrieved_at timestamps.
5. Strict audit logging and error reporting without ever fabricating synthetic fallback data.
"""
import logging
import time
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing
from apps.market.models import DataQualityIssue, HistoricalCandle
from integrations.market_data.exceptions import (
    ProviderConnectionError,
    RateLimitError,
)
from integrations.market_data.registry import ProviderRegistry
from services.calendar.exchange_calendar import ExchangeCalendar
from services.market_data.historical_pipeline import (
    PROVIDER_PRECEDENCE,
    HistoricalDataIngestionPipeline,
)

logger = logging.getLogger(__name__)

PILOT_SYMBOLS = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "SBIN",
    "LT",
    "ITC",
    "BHARTIARTL",
    "20MICRONS",
    "XPROINDIA",
]
BENCHMARK_SYMBOL = "^NSEI"


class EODIngestionService:
    """
    Service for automated end-of-day market data ingestion and readiness synchronization.
    """

    @classmethod
    def get_or_register_pilot_listings(cls, universe: list[str] | None = None) -> list[ExchangeListing]:
        """
        Retrieves or provisions ExchangeListings for the benchmark and pilot universe.
        """
        pipeline = HistoricalDataIngestionPipeline()
        benchmark = pipeline.register_or_get_benchmark_listing()

        target_symbols = universe if universe is not None else PILOT_SYMBOLS
        nse, _ = Exchange.objects.get_or_create(
            code="NSE",
            defaults={"name": "National Stock Exchange of India"},
        )

        listings = [benchmark]
        for sym in target_symbols:
            listing = ExchangeListing.objects.filter(exchange=nse, symbol=sym).first()
            if not listing:
                # Fallback to any exchange
                listing = ExchangeListing.objects.filter(symbol=sym).first()
            if listing:
                listings.append(listing)
            else:
                logger.warning("Listing not found for pilot symbol: %s", sym)

        return listings

    @classmethod
    def ingest_session_eod(
        cls,
        session_date: date | None = None,
        universe: list[str] | None = None,
        primary_provider: str = "YAHOO",
        fallback_provider: str = "JUGAAD",
        max_retries: int = 3,
        rate_limit_delay_seconds: float = 0.5,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Executes automated EOD ingestion for the requested session date.
        """
        start_time = time.time()
        now_ist = datetime.now(ExchangeCalendar.IST)

        if session_date is None:
            if now_ist.time() >= ExchangeCalendar.MARKET_CLOSE_TIME:
                session_date = now_ist.date()
            else:
                session_date = ExchangeCalendar.get_last_trading_day(now_ist.date())

        result: dict[str, Any] = {
            "session_date": session_date,
            "status": "FAILED",
            "is_trading_day": False,
            "holiday_reason": None,
            "total_symbols": 0,
            "symbols_succeeded": 0,
            "succeeded_symbols": [],
            "missing_symbols": [],
            "candles_ingested": 0,
            "errors": [],
            "duration_seconds": 0.0,
            "dry_run": dry_run,
        }

        # 1. Exchange Trading Calendar Validation
        is_trading = ExchangeCalendar.is_trading_day(session_date)
        result["is_trading_day"] = is_trading
        if not is_trading:
            holiday = ExchangeCalendar.get_holiday_reason(session_date) or "Weekend / Exchange Holiday"
            result["holiday_reason"] = holiday
            result["status"] = "SKIPPED_HOLIDAY"
            result["reason"] = f"Date {session_date} is not an active exchange trading session ({holiday})."
            result["duration_seconds"] = round(time.time() - start_time, 2)
            logger.info("EOD Ingestion skipped for %s: %s", session_date, holiday)
            return result

        # 2. Market Close Time Check (if session is today)
        if session_date == now_ist.date() and now_ist.time() < ExchangeCalendar.MARKET_CLOSE_TIME:
            result["status"] = "WAITING_FOR_DATA"
            result["reason"] = f"Trading session for {session_date} is still open (current IST: {now_ist.time().strftime('%H:%M:%S')})."
            result["duration_seconds"] = round(time.time() - start_time, 2)
            logger.info("EOD Ingestion waiting for market close: %s", result["reason"])
            return result

        # 3. Collect Target Listings (Pilot Equities + Benchmark)
        listings = cls.get_or_register_pilot_listings(universe=universe)
        result["total_symbols"] = len(listings)

        if not listings:
            result["status"] = "FAILED"
            result["reason"] = "No target exchange listings configured for ingestion."
            result["duration_seconds"] = round(time.time() - start_time, 2)
            return result

        candles_ingested = 0
        succeeded_symbols = []
        missing_symbols = []
        errors = []

        providers_to_try = [primary_provider.upper()]
        if fallback_provider and fallback_provider.upper() != primary_provider.upper():
            providers_to_try.append(fallback_provider.upper())

        for listing in listings:
            sym = listing.symbol
            candle_fetched = False
            last_sym_error = None

            for prov_code in providers_to_try:
                try:
                    provider = ProviderRegistry.get(prov_code)
                except Exception as reg_err:
                    logger.debug("Provider %s not in registry: %s", prov_code, reg_err)
                    continue

                for attempt in range(1, max_retries + 1):
                    if rate_limit_delay_seconds > 0:
                        time.sleep(rate_limit_delay_seconds)

                    try:
                        candles_raw = provider.get_historical_candles(
                            listing=listing,
                            start_date=session_date,
                            end_date=session_date,
                            interval="1d",
                        )
                        if candles_raw:
                            # Match target session date exactly
                            target_candle = next(
                                (
                                    c for c in candles_raw
                                    if (c.timestamp.astimezone(ExchangeCalendar.IST).date()
                                    if hasattr(c.timestamp, "astimezone")
                                    else c.timestamp.date()) == session_date
                                ),
                                None,
                            )
                            if target_candle:
                                if not dry_run:
                                    cls._upsert_candle(listing, target_candle, prov_code)
                                candle_fetched = True
                                candles_ingested += 1
                                succeeded_symbols.append(sym)
                                break
                    except (ProviderConnectionError, RateLimitError, Exception) as exc:
                        last_sym_error = str(exc)
                        logger.warning(
                            "[%s] Attempt %d/%d via %s failed: %s",
                            sym, attempt, max_retries, prov_code, exc,
                        )
                        if attempt < max_retries:
                            time.sleep(rate_limit_delay_seconds * (2 ** (attempt - 1)))

                if candle_fetched:
                    break

            if not candle_fetched:
                missing_symbols.append(sym)
                err_detail = {
                    "symbol": sym,
                    "error": last_sym_error or "Zero authentic candles returned by configured providers.",
                    "providers_attempted": providers_to_try,
                }
                errors.append(err_detail)
                if not dry_run:
                    DataQualityIssue.objects.create(
                        listing=listing,
                        issue_type="PROVIDER_DISCREPANCY",
                        severity="MEDIUM",
                        details={
                            "session_date": session_date.isoformat(),
                            "error": err_detail["error"],
                            "providers": providers_to_try,
                        },
                    )

        result["candles_ingested"] = candles_ingested
        result["symbols_succeeded"] = len(succeeded_symbols)
        result["succeeded_symbols"] = succeeded_symbols
        result["missing_symbols"] = missing_symbols
        result["errors"] = errors
        result["duration_seconds"] = round(time.time() - start_time, 2)

        # 4. Strict Readiness Status Determination
        total_count = len(listings)
        success_count = len(succeeded_symbols)

        if success_count == total_count:
            result["status"] = "SUCCESS"
            result["reason"] = f"All {total_count} universe instruments ingested successfully for {session_date}."
        elif success_count > 0:
            result["status"] = "DEGRADED"
            result["reason"] = f"Partial ingestion: {success_count}/{total_count} instruments succeeded; missing: {', '.join(missing_symbols)}."
        else:
            # 0 succeeded: check if past session or today
            if session_date == now_ist.date():
                result["status"] = "WAITING_FOR_DATA"
                result["reason"] = f"0/{total_count} instruments available yet from authentic providers for session {session_date}."
            else:
                result["status"] = "FAILED"
                result["reason"] = f"All provider attempts failed for session {session_date}. Missing 100% of pilot data."

        logger.info(
            "EOD Ingestion completed for %s: Status=%s (%d/%d succeeded, %d candles, %.2fs).",
            session_date,
            result["status"],
            success_count,
            total_count,
            candles_ingested,
            result["duration_seconds"],
        )
        return result

    @classmethod
    def _upsert_candle(cls, listing: ExchangeListing, candle_dto: Any, provider_code: str) -> None:
        """
        Idempotent upsert of authentic HistoricalCandle respecting source precedence.
        """
        incoming_priority = PROVIDER_PRECEDENCE.get(provider_code.upper(), 50)
        now_utc = timezone.now()

        with transaction.atomic():
            existing = (
                HistoricalCandle.objects.select_for_update()
                .filter(listing=listing, timestamp=candle_dto.timestamp, interval=candle_dto.interval)
                .first()
            )

            if existing:
                existing_priority = PROVIDER_PRECEDENCE.get(existing.source_provider, 0)
                if incoming_priority < existing_priority:
                    # Do not overwrite higher priority data (e.g. EXCHANGE/BHAVCOPY with YAHOO)
                    return

                existing.open = candle_dto.open
                existing.high = candle_dto.high
                existing.low = candle_dto.low
                existing.close = candle_dto.close
                existing.volume = candle_dto.volume
                if candle_dto.adjusted_close is not None:
                    existing.adjusted_close = candle_dto.adjusted_close
                existing.source_provider = provider_code.upper()
                existing.retrieved_at = now_utc
                existing.save()
            else:
                HistoricalCandle.objects.create(
                    listing=listing,
                    timestamp=candle_dto.timestamp,
                    interval=candle_dto.interval,
                    open=candle_dto.open,
                    high=candle_dto.high,
                    low=candle_dto.low,
                    close=candle_dto.close,
                    volume=candle_dto.volume,
                    adjusted_close=candle_dto.adjusted_close,
                    source_provider=provider_code.upper(),
                )
