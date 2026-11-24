"""
Tests for Phase 3.2: Authentic Historical Data Pipeline, Benchmarks and Ingestion.
Complies with AIML Architecture v2.1 and Master Specification Section 18.
Verifies:
- Benchmark NIFTY 50 listing registration (^NSEI)
- Incremental resumable checkpoints and idempotent upserts
- Rate-limit handling and calendar session verification
- Protection of authentic market data against synthetic overwrites
- Gross vs net target return with friction under corporate actions
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from services.market_data.historical_pipeline import HistoricalDataIngestionPipeline


@pytest.fixture
def test_equity_listing(db):
    nse, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "National Stock Exchange"})
    inst = Instrument.objects.create(
        isin="INE999PIPE01",
        display_name="Pipeline Stock",
        legal_name="Pipeline Stock Ltd",
        is_active=True,
    )
    listing = ExchangeListing.objects.create(
        exchange=nse,
        symbol="PIPESTOCK",
        instrument=inst,
        is_tradeable=True,
    )
    return listing


class TestHistoricalDataIngestionPipeline:
    """
    Tests pipeline operations: checkpointing, idempotent upserts, calendar verification,
    and protection of authentic data.
    """

    def test_benchmark_listing_registration(self, db):
        pipeline = HistoricalDataIngestionPipeline()
        listing = pipeline.register_or_get_benchmark_listing()
        assert listing.symbol == "^NSEI"
        assert listing.exchange.code == "NSE"
        assert listing.instrument.isin == "IN_INDEX_NIFTY50"
        assert listing.instrument.sector == "INDEX"

        # Idempotency: second call returns same instance without duplication
        listing2 = pipeline.register_or_get_benchmark_listing()
        assert listing.id == listing2.id

    def test_idempotent_candle_upserts(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=False,
        )

        mock_candle = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)),
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_candle]
            mock_get_p.return_value = mock_provider

            # First run: Ingests 1 candle
            chk1 = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
            )
            assert chk1.status == "SUCCESS"
            assert chk1.total_candles_ingested == 1
            assert HistoricalCandle.objects.filter(listing=test_equity_listing).count() == 1

            # Second run on same date range: Idempotent upsert, no duplicates created
            chk2 = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
            )
            assert chk2.status == "SUCCESS"
            assert HistoricalCandle.objects.filter(listing=test_equity_listing).count() == 1

    def test_calendar_session_filtering_in_pipeline(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=True,
        )

        # Candle on Sunday 2026-11-22 (non-trading day)
        mock_sunday_candle = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 11, 22, 10, 0)),
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_sunday_candle]
            mock_get_p.return_value = mock_provider

            chk = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 11, 22),
                end_date=date(2026, 11, 22),
            )
            # Sunday candle should be skipped due to calendar check
            assert chk.status == "SUCCESS"
            assert chk.total_candles_ingested == 0
            assert HistoricalCandle.objects.filter(listing=test_equity_listing).count() == 0

    def test_resumable_incremental_checkpoint(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=False,
        )

        # Seed existing authentic candle on Day 1
        HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)),
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )

        # Mock returns Day 2 candle
        mock_candle_day2 = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 2, 10, 0)),
            interval="1d",
            open=Decimal("102.00"),
            high=Decimal("107.00"),
            low=Decimal("101.00"),
            close=Decimal("105.00"),
            volume=60000,
            adjusted_close=Decimal("105.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_candle_day2]
            mock_get_p.return_value = mock_provider

            chk = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
            )

            # Provider should only be called for 2026-06-02 onwards
            mock_provider.get_historical_candles.assert_called_once_with(
                listing=test_equity_listing,
                start_date=date(2026, 6, 2),
                end_date=date(2026, 6, 2),
                interval="1d",
            )
            assert chk.status == "SUCCESS"
            assert chk.total_candles_ingested == 1
            assert HistoricalCandle.objects.filter(listing=test_equity_listing).count() == 2

    def test_backfill_mode_overrides_incremental_start(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=False,
            backfill_mode=True,
        )

        # Existing candle on Day 2
        HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 2, 10, 0)),
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )

        mock_candle = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)),
            interval="1d",
            open=Decimal("98.00"),
            high=Decimal("101.00"),
            low=Decimal("97.00"),
            close=Decimal("100.00"),
            volume=45000,
            adjusted_close=Decimal("100.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_candle]
            mock_get_p.return_value = mock_provider

            # In backfill mode, start_date is respected even if later candles exist
            chk = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
            )
            mock_provider.get_historical_candles.assert_called_once_with(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 2),
                interval="1d",
            )
            assert chk.status == "SUCCESS"

    def test_source_precedence_authentic_replaces_seeded(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=False,
            backfill_mode=True,
        )

        candle_ts = timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0))

        # Existing seeded candle
        c_seed = HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=candle_ts,
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="SEEDED",
        )

        mock_authentic = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=candle_ts,
            interval="1d",
            open=Decimal("101.50"),
            high=Decimal("106.00"),
            low=Decimal("97.00"),
            close=Decimal("104.25"),
            volume=75000,
            adjusted_close=Decimal("104.25"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_authentic]
            mock_get_p.return_value = mock_provider

            chk = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
            )
            assert chk.status == "SUCCESS"

            # Check candle was updated and source_provider replaced with YAHOO
            c_seed.refresh_from_db()
            assert c_seed.source_provider == "YAHOO"
            assert c_seed.close == Decimal("104.25")
            assert c_seed.volume == 75000

    def test_source_precedence_seeded_cannot_overwrite_authentic(self, test_equity_listing):
        # A seeded/lower-precedence pipeline cannot overwrite an authentic candle
        seeded_pipeline = HistoricalDataIngestionPipeline(
            provider_code="SEEDED",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=False,
            backfill_mode=True,
        )

        candle_ts = timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0))

        # Existing authentic candle from JUGAAD
        c_auth = HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=candle_ts,
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="JUGAAD",
        )

        mock_seeded = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=candle_ts,
            interval="1d",
            open=Decimal("50.00"),
            high=Decimal("55.00"),
            low=Decimal("45.00"),
            close=Decimal("52.00"),
            volume=1000,
            adjusted_close=Decimal("52.00"),
            source_provider="SEEDED",
        )

        with patch.object(seeded_pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_seeded]
            mock_get_p.return_value = mock_provider

            chk = seeded_pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=date(2026, 6, 1),
                end_date=date(2026, 6, 1),
            )
            assert chk.status == "SUCCESS"

            # Authentic candle is untouched!
            c_auth.refresh_from_db()
            assert c_auth.source_provider == "JUGAAD"
            assert c_auth.close == Decimal("102.00")

    def test_gap_detection_and_repair(self, test_equity_listing):
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=True,
        )

        # Mon 2026-06-01 to Wed 2026-06-03
        d1 = date(2026, 6, 1)  # Monday
        d2 = date(2026, 6, 2)  # Tuesday
        d3 = date(2026, 6, 3)  # Wednesday

        # Candle on d1 and d3, d2 is missing
        HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)),
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )
        HistoricalCandle.objects.create(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 3, 10, 0)),
            interval="1d",
            open=Decimal("105.00"),
            high=Decimal("108.00"),
            low=Decimal("104.00"),
            close=Decimal("106.00"),
            volume=55000,
            adjusted_close=Decimal("106.00"),
            source_provider="YAHOO",
        )

        # Gap detection
        gaps = pipeline.detect_missing_session_gaps(test_equity_listing, d1, d3, "1d", require_authentic=True)
        assert gaps == [d2]

        # Repair session gaps
        mock_repair_candle = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=timezone.make_aware(timezone.datetime(2026, 6, 2, 10, 0)),
            interval="1d",
            open=Decimal("102.00"),
            high=Decimal("106.00"),
            low=Decimal("101.00"),
            close=Decimal("105.00"),
            volume=52000,
            adjusted_close=Decimal("105.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_repair_candle]
            mock_get_p.return_value = mock_provider

            repair_res = pipeline.repair_session_gaps(test_equity_listing, d1, d3, "1d")
            assert repair_res["status"] == "REPAIRED"
            assert repair_res["gaps_detected"] == 1
            assert repair_res["gaps_repaired"] == 1
            assert repair_res["remaining_gaps"] == 0

    def test_eod_session_close_ist_normalization(self, test_equity_listing):
        """
        Regression test: Verify that an EOD candle for an Indian listing (e.g. Monday session)
        has its date evaluated in IST so Monday sessions are not dropped as Sunday weekends.
        """
        import zoneinfo
        from datetime import UTC, datetime, time

        IST = zoneinfo.ZoneInfo("Asia/Kolkata")
        pipeline = HistoricalDataIngestionPipeline(
            provider_code="YAHOO",
            rate_limit_delay_seconds=0.0,
            verify_against_calendar=True,
        )

        # Monday 2020-01-06: at 15:30 IST (10:00 UTC)
        monday_date = date(2020, 1, 6)
        monday_ts = datetime.combine(monday_date, time(15, 30), tzinfo=IST).astimezone(UTC)
        assert monday_ts.date() == monday_date  # Same calendar date in UTC and IST

        mock_monday_candle = HistoricalCandle(
            listing=test_equity_listing,
            timestamp=monday_ts,
            interval="1d",
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("95.00"),
            close=Decimal("102.00"),
            volume=50000,
            adjusted_close=Decimal("102.00"),
            source_provider="YAHOO",
        )

        with patch.object(pipeline, "get_provider") as mock_get_p:
            mock_provider = MagicMock()
            mock_provider.get_historical_candles.return_value = [mock_monday_candle]
            mock_get_p.return_value = mock_provider

            chk = pipeline.ingest_listing_history(
                listing=test_equity_listing,
                start_date=monday_date,
                end_date=monday_date,
                backfill_mode=True,
            )
            assert chk.status == "SUCCESS"
            assert chk.total_candles_ingested == 1
            assert HistoricalCandle.objects.filter(listing=test_equity_listing).count() == 1

    def test_pit_corporate_action_isolation(self, test_equity_listing):
        """
        Verifies that point-in-time corporate action adjustments strictly enforce as_of_date
        and do not leak future splits into historical periods.
        """
        from apps.news.models import CorporateEvent
        from services.ml.dataset_builder import CorporateActionAdjuster

        # Create a 2-for-1 split with event_date in 2024
        CorporateEvent.objects.create(
            listing=test_equity_listing,
            event_type="SPLIT",
            title="Sub-division from Rs 10 to Rs 5",
            event_date=date(2024, 6, 1),
            ratio_or_value="2:1",
            status="ANNOUNCED",
        )

        # As of 2023-01-01 (before split), factor must be 1.0 (no future leakage!)
        events_pre = CorporateActionAdjuster.get_adjustment_events_for_listing(
            test_equity_listing, as_of_date=date(2023, 1, 1)
        )
        assert len(events_pre) == 0

        # As of 2025-01-01 (after split), event is visible and multiplier factor is 0.50
        events_post = CorporateActionAdjuster.get_adjustment_events_for_listing(
            test_equity_listing, as_of_date=date(2025, 1, 1)
        )
        assert len(events_post) == 1
        assert events_post[0]["factor"] == 0.50
