"""
Central MarketDataService Orchestrator.
Applies caching, provider routing, fallback execution, and data quality validation.
"""
import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from apps.market.models import (
    DataProvider,
    DataQualityIssue,
    DataRefreshLog,
    HistoricalCandle,
    MarketQuote,
)
from integrations.market_data.base import (
    FreshnessStatus,
    HistoricalCandleDTO,
    MarketQuoteDTO,
)
from integrations.market_data.exceptions import (
    DataQualityError,
    MarketDataError,
    ProviderConnectionError,
    RateLimitError,
)
from integrations.market_data.health import ProviderHealthMonitor
from integrations.market_data.normalizer import MarketDataNormalizer
from integrations.market_data.registry import ProviderRegistry
from services.calendar.exchange_calendar import ExchangeCalendar

logger = logging.getLogger(__name__)

class MarketDataService:
    QUOTE_CACHE_TTL = 30  # seconds

    @classmethod
    def get_quote(cls, listing: ExchangeListing, force_refresh: bool = False) -> MarketQuote:
        """
        Retrieves latest quote for an exchange listing.
        Checks cache -> attempts primary provider -> falls back to secondary provider.
        """
        cache_key = f"market:quote:{listing.exchange.code}:{listing.symbol}"

        # 1. Check in-memory/Redis cache
        if not force_refresh:
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_age = (timezone.now() - cached_data.retrieved_at).total_seconds()
                is_stale = ExchangeCalendar.is_market_open() and (cached_age > 300)
                freshness = FreshnessStatus.STALE if is_stale else FreshnessStatus.CACHED

                # Return updated freshness representation without writing to DB
                return MarketQuote(
                    listing=listing,
                    price=cached_data.price,
                    change=cached_data.change,
                    change_percent=cached_data.change_percent,
                    open=cached_data.open,
                    high=cached_data.high,
                    low=cached_data.low,
                    close=cached_data.close,
                    previous_close=cached_data.previous_close,
                    volume=cached_data.volume,
                    source_provider=cached_data.source_provider,
                    source_type=cached_data.source_type,
                    freshness_status=freshness.value,
                    source_timestamp=cached_data.source_timestamp,
                    retrieved_at=cached_data.retrieved_at,
                    measured_latency_ms=cached_data.measured_latency_ms,
                    configured_delay_minutes=cached_data.configured_delay_minutes,
                )

        # 2. Query provider pipeline with fallback
        providers = ProviderRegistry.get_all()
        last_error = None
        quote_dto: MarketQuoteDTO | None = None

        for provider in providers:
            if not ProviderHealthMonitor.is_provider_available(provider.code):
                logger.warning("Skipping unavailable / circuit-broken provider: %s", provider.code)
                continue

            try:
                logger.info("Attempting quote fetch for %s via %s", listing.symbol, provider.code)
                quote_dto = provider.get_quote(listing)
                break
            except (ProviderConnectionError, RateLimitError, MarketDataError) as e:
                logger.warning("Provider %s failed for %s: %s", provider.code, listing.symbol, e)
                last_error = e
                # Record fallback incident if failing from primary
                if provider == providers[0]:
                    DataQualityIssue.objects.create(
                        listing=listing,
                        issue_type="PROVIDER_DISCREPANCY",
                        severity="MEDIUM",
                        details={"error": str(e), "primary_provider": provider.code, "action": "fallback_routing"},
                    )

        if not quote_dto:
            # Check if we have an existing quote in database to serve as OFFLINE fallback
            existing = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
            if existing:
                existing.freshness_status = FreshnessStatus.OFFLINE.value
                return existing

            # Check if we have historical candle data to construct an offline fallback quote
            latest_candle = HistoricalCandle.objects.filter(listing=listing).order_by("-timestamp").first()
            if latest_candle:
                prev_candle = (
                    HistoricalCandle.objects.filter(listing=listing, timestamp__lt=latest_candle.timestamp)
                    .order_by("-timestamp")
                    .first()
                )
                prev_close = prev_candle.close if prev_candle else latest_candle.close
                change = latest_candle.close - prev_close
                change_pct = (change / prev_close * 100) if prev_close else Decimal("0")
                return MarketQuote(
                    listing=listing,
                    price=latest_candle.close,
                    change=change,
                    change_percent=change_pct,
                    open=latest_candle.open,
                    high=latest_candle.high,
                    low=latest_candle.low,
                    close=latest_candle.close,
                    previous_close=prev_close,
                    volume=latest_candle.volume,
                    source_provider=latest_candle.source_provider or "HISTORICAL",
                    source_type="DELAYED",
                    freshness_status=FreshnessStatus.OFFLINE.value,
                    source_timestamp=latest_candle.timestamp,
                    retrieved_at=timezone.now(),
                    measured_latency_ms=0,
                    configured_delay_minutes=1440,
                )

            raise ProviderConnectionError(
                f"Unable to retrieve quote for {listing.symbol} from any configured provider. Last error: {last_error}"
            )

        # 3. Persist and cache validated quote
        with transaction.atomic():
            quote_model = MarketQuote.objects.create(
                listing=listing,
                price=quote_dto.price,
                change=quote_dto.change,
                change_percent=quote_dto.change_percent,
                open=quote_dto.open,
                high=quote_dto.high,
                low=quote_dto.low,
                close=quote_dto.close,
                previous_close=quote_dto.previous_close,
                volume=quote_dto.volume,
                source_provider=quote_dto.source_provider,
                source_type=quote_dto.source_type.value,
                freshness_status=quote_dto.freshness_status.value,
                source_timestamp=quote_dto.source_timestamp,
                retrieved_at=quote_dto.retrieved_at,
                measured_latency_ms=quote_dto.measured_latency_ms,
                configured_delay_minutes=quote_dto.configured_delay_minutes,
            )

        cache.set(cache_key, quote_model, cls.QUOTE_CACHE_TTL)
        return quote_model

    @classmethod
    def get_historical_candles(
        cls,
        listing: ExchangeListing,
        start_date: date,
        end_date: date,
        interval: str = "1d",
        fetch_if_missing: bool = True,
    ) -> list[HistoricalCandle]:
        """
        Retrieves historical candle series from PostgreSQL; backfills from provider if missing.
        """
        start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
        end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)

        existing_candles = list(
            HistoricalCandle.objects.filter(
                listing=listing,
                interval=interval,
                timestamp__gte=start_dt,
                timestamp__lte=end_dt,
            ).order_by("timestamp")
        )

        if existing_candles or not fetch_if_missing:
            return existing_candles

        # Fetch from providers
        providers = ProviderRegistry.get_all()
        candle_dtos: list[HistoricalCandleDTO] = []
        last_error = None

        for provider in providers:
            try:
                logger.info("Fetching historical data for %s from %s", listing.symbol, provider.code)
                candle_dtos = provider.get_historical_candles(listing, start_date, end_date, interval=interval)
                if candle_dtos:
                    break
            except Exception as e:
                logger.warning("Historical fetch via %s failed for %s: %s", provider.code, listing.symbol, e)
                last_error = e

        if not candle_dtos and last_error:
            raise ProviderConnectionError(f"Failed to fetch historical candles: {last_error}")

        # Bulk create with ignore_conflicts for idempotency
        new_records = [
            HistoricalCandle(
                listing=listing,
                timestamp=c.timestamp,
                interval=c.interval,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
                adjusted_close=c.adjusted_close,
                source_provider=c.source_provider,
            )
            for c in candle_dtos
        ]

        HistoricalCandle.objects.bulk_create(new_records, ignore_conflicts=True)

        return list(
            HistoricalCandle.objects.filter(
                listing=listing,
                interval=interval,
                timestamp__gte=start_dt,
                timestamp__lte=end_dt,
            ).order_by("timestamp")
        )

    @classmethod
    def ingest_eod_bhavcopy(cls, target_date: date) -> int:
        """
        Ingests official NSE daily Bhavcopy for all equities on target_date.
        Respects ExchangeCalendar; rejects non-trading days.
        """
        if not ExchangeCalendar.is_trading_day(target_date):
            logger.info("Skipping Bhavcopy ingestion for %s (Non-trading day/holiday)", target_date)
            return 0

        provider_obj, _ = DataProvider.objects.get_or_create(
            code="JUGAAD",
            defaults={"name": "Jugaad-Data (NSE India)", "priority": 1},
        )
        log = DataRefreshLog.objects.create(
            provider=provider_obj,
            data_type="BHAVCOPY",
            status="SUCCESS",
            started_at=timezone.now(),
        )

        try:
            import tempfile

            import pandas as pd
            from jugaad_data.nse import bhavcopy_save

            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = bhavcopy_save(target_date, tmpdir)
                df = pd.read_csv(file_path)

            records_count = 0
            candles_to_create = []

            for _, row in df.iterrows():
                series = str(row.get("SERIES", "")).strip()
                if series != "EQ":
                    continue

                symbol = str(row.get("SYMBOL", "")).strip()
                listing = ExchangeListing.objects.filter(symbol=symbol, exchange_id="NSE").first()
                if not listing:
                    continue

                candle_ts = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
                open_val = Decimal(str(row.get("OPEN", 0)))
                high_val = Decimal(str(row.get("HIGH", 0)))
                low_val = Decimal(str(row.get("LOW", 0)))
                close_val = Decimal(str(row.get("CLOSE", 0)))
                vol_val = int(row.get("TOTTRDQTY", 0))

                try:
                    c_dto = HistoricalCandleDTO(
                        timestamp=candle_ts,
                        interval="1d",
                        open=open_val,
                        high=high_val,
                        low=low_val,
                        close=close_val,
                        volume=vol_val,
                        adjusted_close=None,
                        source_provider="JUGAAD",
                    )
                    valid_c = MarketDataNormalizer.validate_candle(c_dto)
                    candles_to_create.append(
                        HistoricalCandle(
                            listing=listing,
                            timestamp=valid_c.timestamp,
                            interval=valid_c.interval,
                            open=valid_c.open,
                            high=valid_c.high,
                            low=valid_c.low,
                            close=valid_c.close,
                            volume=valid_c.volume,
                            adjusted_close=valid_c.adjusted_close,
                            source_provider=valid_c.source_provider,
                        )
                    )
                    records_count += 1
                except DataQualityError as dq_err:
                    DataQualityIssue.objects.create(
                        listing=listing,
                        issue_type="INVALID_OHLC",
                        severity="HIGH",
                        details={"error": str(dq_err), "raw_row": row.to_dict()},
                    )

            HistoricalCandle.objects.bulk_create(candles_to_create, ignore_conflicts=True)
            log.records_ingested = records_count
            log.completed_at = timezone.now()
            log.save()
            return records_count
        except Exception as e:
            log.status = "FAILED"
            log.completed_at = timezone.now()
            log.error_details = str(e)
            log.save()
            logger.error("Bhavcopy ingestion failed for %s: %s", target_date, e)
            raise
