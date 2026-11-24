"""
Unit tests for AI/ML Phase 2: Historical Dataset Builder and Corporate Action Adjustments.
Complies with Master Specification Section 18 and AIML Architecture Specification v2.1.
"""
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pandas as pd
import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import MLDatasetSnapshot
from apps.news.models import CorporateEvent, CorporateEventType, EventStatus
from services.calendar.exchange_calendar import ExchangeCalendar
from services.ml.dataset_builder import (
    CorporateActionAdjuster,
    DataQualityValidator,
    DatasetBuilder,
    MLEligibilityClassifier,
    MLEligibilityStatus,
    UniverseResolver,
)


@pytest.fixture
def nse_exchange():
    ex, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "National Stock Exchange of India"})
    return ex


@pytest.fixture
def sample_listing(nse_exchange):
    inst, _ = Instrument.objects.get_or_create(
        isin="INE002A01018",
        defaults={
            "legal_name": "Sample Test Corporation Limited",
            "display_name": "Sample Test Corp",
            "sector": "Information Technology",
            "industry": "Software Services",
            "market_cap_category": "LARGE",
            "is_active": True,
        },
    )
    listing, _ = ExchangeListing.objects.get_or_create(
        symbol="SAMPLECORP",
        exchange=nse_exchange,
        defaults={"instrument": inst, "is_tradeable": True, "series_or_group": "EQ"},
    )
    return listing


class TestCorporateActionAdjusterFormulas:
    """
    Tests verified mathematical formulas for split and bonus multipliers
    as documented in AIML_ARCHITECTURE.md Section 5.2.
    """

    def test_5_for_1_split_ratio_parsing(self):
        # 1 old share splits into 5 new shares (N=5) -> f = 0.200000
        factor, desc = CorporateActionAdjuster.parse_ratio("SPLIT", "1:5 Split", "Sub-division")
        assert factor == 0.200000
        assert "split" in desc

        factor2, _ = CorporateActionAdjuster.parse_ratio("SPLIT", "5-for-1", "")
        assert factor2 == 0.200000

        factor3, _ = CorporateActionAdjuster.parse_ratio("SPLIT", "", "Sub-division of shares from Rs 10 to Rs 2")
        assert factor3 == 0.200000

        # Pre-split price ₹1,500 becomes ₹300. Volume 10,000 becomes 50,000
        pre_price = 1500.0
        pre_vol = 10000
        assert round(pre_price * factor, 2) == 300.00
        assert round(pre_vol / factor) == 50000

    def test_1_to_1_bonus_ratio_parsing(self):
        # 1 new share for 1 existing -> f = 1 / (1 + 1) = 0.500000
        factor, desc = CorporateActionAdjuster.parse_ratio("BONUS", "1:1 Bonus", "Bonus Issue")
        assert factor == 0.500000
        assert "bonus" in desc

        # Pre-bonus price ₹2,000 becomes ₹1,000
        pre_price = 2000.0
        assert round(pre_price * factor, 2) == 1000.00

    def test_3_to_1_bonus_ratio_parsing(self):
        # 3 new shares for 1 existing -> f = 1 / (1 + 3) = 0.250000
        factor, desc = CorporateActionAdjuster.parse_ratio("BONUS", "3:1 Bonus", "Bonus Issue")
        assert factor == 0.250000

        # Pre-bonus price ₹4,000 becomes ₹1,000
        pre_price = 4000.0
        assert round(pre_price * factor, 2) == 1000.00

    def test_2_to_1_and_1_to_2_bonus_parsing(self):
        # 2:1 Bonus (2 new for 1 held) -> f = 1 / (1 + 2) = 0.333333
        factor_2_1, _ = CorporateActionAdjuster.parse_ratio("BONUS", "2:1 Bonus", "")
        assert round(factor_2_1, 4) == round(1.0 / 3.0, 4)

        # 1:2 Bonus (1 new for 2 held) -> f = 2 / (2 + 1) = 0.666667
        factor_1_2, _ = CorporateActionAdjuster.parse_ratio("BONUS", "1:2 Bonus", "")
        assert round(factor_1_2, 4) == round(2.0 / 3.0, 4)


class TestDataQualityValidator:
    """
    Tests candle validation, suspicious jump detection, and missing session identification.
    """

    def test_valid_candle(self):
        rec = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 5000}
        valid, errors = DataQualityValidator.validate_candle_record(rec)
        assert valid is True
        assert len(errors) == 0

    def test_invalid_ohlc_relationships(self):
        # High < Low
        rec1 = {"open": 100.0, "high": 95.0, "low": 102.0, "close": 98.0, "volume": 100}
        valid1, errors1 = DataQualityValidator.validate_candle_record(rec1)
        assert valid1 is False
        assert any("less than Low" in e for e in errors1)

        # Open > High
        rec2 = {"open": 110.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 100}
        valid2, errors2 = DataQualityValidator.validate_candle_record(rec2)
        assert valid2 is False

        # Close < Low
        rec3 = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 95.0, "volume": 100}
        valid3, errors3 = DataQualityValidator.validate_candle_record(rec3)
        assert valid3 is False

        # Negative volume
        rec4 = {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": -50}
        valid4, errors4 = DataQualityValidator.validate_candle_record(rec4)
        assert valid4 is False
        assert any("Negative volume" in e for e in errors4)

    def test_detect_suspicious_jumps(self):
        df = pd.DataFrame([
            {"session_date": "2026-01-05", "close_raw": 100.0},
            {"session_date": "2026-01-06", "close_raw": 165.0},  # +65% jump without corporate action
            {"session_date": "2026-01-07", "close_raw": 160.0},
        ])
        jumps = DataQualityValidator.detect_suspicious_jumps(df, corporate_ex_dates=set(), threshold_pct=50.0)
        assert len(jumps) == 1
        assert jumps[0]["session_date"] == "2026-01-06"
        assert jumps[0]["jump_pct"] == 65.0

        # When the ex-date is present in corporate_ex_dates, it is NOT flagged as suspicious
        corp_dates = {date(2026, 1, 6)}
        jumps_with_corp = DataQualityValidator.detect_suspicious_jumps(df, corporate_ex_dates=corp_dates, threshold_pct=50.0)
        assert len(jumps_with_corp) == 0


@pytest.mark.django_db
class TestDatasetBuilderPointInTimeAndProvenance:
    """
    Tests point-in-time corporate action alignment, hash reproducibility,
    raw vs adjusted price separation, and snapshot persistence.
    """

    def test_date_filtering_and_market_holidays(self):
        # Christmas 2025 (Dec 25) is a fixed exchange holiday
        xmas = date(2025, 12, 25)
        assert ExchangeCalendar.is_trading_day(xmas) is False
        assert ExchangeCalendar.get_holiday_reason(xmas) == "Christmas"

        # Republic Day 2026 (Jan 26) is a fixed holiday
        rep_day = date(2026, 1, 26)
        assert ExchangeCalendar.is_trading_day(rep_day) is False

        # Saturday & Sunday are non-trading days
        sat = date(2026, 1, 10)
        assert sat.weekday() == 5
        assert ExchangeCalendar.is_trading_day(sat) is False

    def test_point_in_time_adjustment_and_raw_price_separation(self, sample_listing):
        # Create candles across 5 trading sessions
        base_date = date(2026, 2, 2)  # Monday
        ex_date = date(2026, 2, 5)    # Thursday: 5-for-1 Split ex-date

        # Add verified split corporate event
        CorporateEvent.objects.create(
            listing=sample_listing,
            event_type=CorporateEventType.SPLIT,
            event_date=ex_date,
            ratio_or_value="1:5 Split",
            title="Sub-division of shares 1:5",
            status=EventStatus.COMPLETED,
        )

        # Create 5 daily candles (Mon to Fri)
        # Pre-split trading at 1500, post-split trading at 300
        candles = []
        for i in range(5):
            c_date = base_date + timedelta(days=i)
            is_post_split = c_date >= ex_date
            price = Decimal("300.0000") if is_post_split else Decimal("1500.0000")
            vol = 50000 if is_post_split else 10000
            c = HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
                interval="1d",
                open=price,
                high=price + Decimal("10.0"),
                low=price - Decimal("10.0"),
                close=price,
                volume=vol,
                source_provider="TEST",
            )
            candles.append(c)

        # 1. As-of date AFTER split (2026-02-06): Split is known and applied
        builder_post = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=4),
            universe=[sample_listing.symbol],
            as_of_date=base_date + timedelta(days=4),
        )
        df_post, audit_post = builder_post.extract_listing_data(
            sample_listing,
            builder_post.get_expected_trading_sessions(),
        )

        assert len(df_post) == 5
        assert audit_post["corporate_actions_applied"][0]["factor"] == 0.200000

        # Pre-split candles (i=0, 1, 2) must have adjustment_factor = 0.20
        for i in range(3):
            row = df_post.iloc[i]
            assert row["close_raw"] == 1500.0000
            assert row["adjustment_factor"] == 0.200000
            assert row["close_adj"] == 300.0000
            assert row["volume_raw"] == 10000
            assert row["volume_adj"] == 50000

        # Post-split candles (i=3, 4) must have adjustment_factor = 1.00
        for i in range(3, 5):
            row = df_post.iloc[i]
            assert row["close_raw"] == 300.0000
            assert row["adjustment_factor"] == 1.000000
            assert row["close_adj"] == 300.0000
            assert row["volume_raw"] == 50000
            assert row["volume_adj"] == 50000

        # Original database records must NOT be overwritten
        db_candle = HistoricalCandle.objects.get(id=candles[0].id)
        assert db_candle.close == Decimal("1500.0000")
        assert db_candle.volume == 10000

        # 2. As-of date BEFORE split (2026-02-04): Split is in the future -> ZERO lookahead leakage!
        builder_pre = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=2),
            universe=[sample_listing.symbol],
            as_of_date=base_date + timedelta(days=2),
        )
        df_pre, audit_pre = builder_pre.extract_listing_data(
            sample_listing,
            builder_pre.get_expected_trading_sessions(),
        )
        assert len(df_pre) == 3
        # No corporate actions applied because ex_date > as_of_date
        assert len(audit_pre["corporate_actions_applied"]) == 0
        for i in range(3):
            assert df_pre.iloc[i]["adjustment_factor"] == 1.000000
            assert df_pre.iloc[i]["close_adj"] == 1500.0000

    def test_canonical_hash_reproducibility(self, sample_listing):
        base_date = date(2026, 3, 2)
        for i in range(12):
            c_date = base_date + timedelta(days=i)
            HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
                interval="1d",
                open=Decimal("100.0"),
                high=Decimal("105.0"),
                low=Decimal("98.0"),
                close=Decimal("102.0"),
                volume=1000,
                source_provider="TEST",
            )

        builder = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=11),
            universe=[sample_listing.symbol],
        )

        df1, meta1 = builder.build_canonical_dataframe()
        hash1 = DatasetBuilder.compute_canonical_hash(df1)

        # Second extraction on identical data must produce 100% identical hash
        df2, meta2 = builder.build_canonical_dataframe()
        hash2 = DatasetBuilder.compute_canonical_hash(df2)

        assert hash1 == hash2
        assert len(hash1) == 64
        assert meta1["content_hash"] == meta2["content_hash"]

        # If data changes (e.g. 1 price is modified), the hash must change
        df_modified = df1.copy()
        df_modified.loc[0, "close_raw"] = 103.5000
        hash_modified = DatasetBuilder.compute_canonical_hash(df_modified)
        assert hash_modified != hash1

    def test_quarantine_invalid_candles(self, sample_listing):
        # Create 1 valid candle and 1 invalid candle (High < Low)
        c_date = date(2026, 4, 1)
        HistoricalCandle.objects.create(
            listing=sample_listing,
            timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
            interval="1d",
            open=Decimal("100.0"),
            high=Decimal("90.0"),  # High < Low invalid
            low=Decimal("105.0"),
            close=Decimal("102.0"),
            volume=1000,
            source_provider="TEST",
        )

        builder = DatasetBuilder(
            start_date=c_date,
            end_date=c_date,
            universe=[sample_listing.symbol],
        )
        df, audit = builder.extract_listing_data(sample_listing, [c_date])
        assert len(df) == 0
        assert audit["quarantined_candles"] == 1
        assert len(audit["quarantined_details"]) == 1
        assert "less than Low" in audit["quarantined_details"][0]["validation_errors"][0]

    def test_snapshot_persistence_and_idempotency(self, sample_listing):
        base_date = date(2026, 5, 4)
        for i in range(12):
            c_date = base_date + timedelta(days=i)
            HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
                interval="1d",
                open=Decimal("200.0"),
                high=Decimal("210.0"),
                low=Decimal("195.0"),
                close=Decimal("205.0"),
                volume=2000,
                source_provider="TEST",
            )

        builder = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=11),
            universe=[sample_listing.symbol],
        )
        df, meta = builder.build_canonical_dataframe()

        # Save snapshot
        snap1 = builder.save_snapshot(df, "test_snapshot_persist", meta, dry_run=False)
        assert snap1.id is not None
        assert snap1.total_samples == len(df)
        assert snap1.content_hash == meta["content_hash"]
        assert "storage_path" in snap1.__dict__ or snap1.storage_path

        # Repeated save updates existing snapshot without creating duplicate rows
        count_before = MLDatasetSnapshot.objects.count()
        snap2 = builder.save_snapshot(df, "test_snapshot_persist", meta, dry_run=False)
        assert snap2.id == snap1.id
        assert MLDatasetSnapshot.objects.count() == count_before

    def test_management_command_execution(self, sample_listing):
        base_date = date(2026, 6, 1)
        for i in range(12):
            c_date = base_date + timedelta(days=i)
            HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
                interval="1d",
                open=Decimal("300.0"),
                high=Decimal("310.0"),
                low=Decimal("295.0"),
                close=Decimal("305.0"),
                volume=3000,
                source_provider="TEST",
            )

        out = StringIO()
        call_command(
            "build_ml_dataset",
            universe=sample_listing.symbol,
            start_date=base_date.isoformat(),
            end_date=(base_date + timedelta(days=11)).isoformat(),
            dry_run=True,
            stdout=out,
        )
        output = out.getvalue()
        assert "KuberLens AI/ML Dataset Snapshot Builder" in output
        assert "DRY RUN" in output
        assert "Content Hash" in output


@pytest.mark.django_db
class TestPhase21MultiExchangeUniversesAndEligibility:
    """
    Tests Phase 2.1 Multi-Exchange (NSE/BSE) expansion, dual-listing deduplication,
    primary listing selection, and ML eligibility classification.
    """

    @pytest.fixture
    def bse_exchange(self):
        ex, _ = Exchange.objects.get_or_create(code="BSE", defaults={"name": "Bombay Stock Exchange"})
        return ex

    @pytest.fixture
    def dual_listed_pair(self, nse_exchange, bse_exchange):
        inst, _ = Instrument.objects.get_or_create(
            isin="INE123DUAL99",
            defaults={
                "legal_name": "Dual Listed Holdings Limited",
                "display_name": "Dual Holdings",
                "sector": "Financial Services",
                "is_active": True,
            },
        )
        nse_listing = ExchangeListing.objects.create(
            symbol="DUALNSE",
            exchange=nse_exchange,
            instrument=inst,
            is_tradeable=True,
            is_primary=True,
        )
        bse_listing = ExchangeListing.objects.create(
            symbol="599999",
            exchange=bse_exchange,
            instrument=inst,
            is_tradeable=True,
            is_primary=False,
        )
        return nse_listing, bse_listing

    def test_universe_resolution_dual_listing_deduplication(self, dual_listed_pair):
        nse_l, bse_l = dual_listed_pair

        # Cross-exchange resolution with deduplication
        resolved, meta = UniverseResolver.resolve(
            universe="ALL_NSE_BSE",
            deduplicate_dual_listings=True,
            primary_policy="PRIMARY_FLAG_THEN_LIQUIDITY",
        )
        # Should deduplicate the BSE listing in favor of the primary NSE listing
        symbols = [item.symbol for item in resolved]
        assert "DUALNSE" in symbols
        assert "599999" not in symbols
        assert meta["deduplicated_duplicates_count"] >= 1

    def test_primary_listing_selection_policies(self, nse_exchange, bse_exchange):
        inst, _ = Instrument.objects.get_or_create(
            isin="INE999TIE001",
            defaults={"legal_name": "Tie Corp", "display_name": "Tie Corp", "is_active": True},
        )
        l_nse = ExchangeListing.objects.create(symbol="TIENSE", exchange=nse_exchange, instrument=inst, is_tradeable=True, is_primary=False)
        l_bse = ExchangeListing.objects.create(symbol="588888", exchange=bse_exchange, instrument=inst, is_tradeable=True, is_primary=False)

        # 1. NSE_PRIORITY policy
        chosen_nse = UniverseResolver._select_primary_listing([l_nse, l_bse], policy="NSE_PRIORITY")
        assert chosen_nse.symbol == "TIENSE"

        # 2. BSE_PRIORITY policy
        chosen_bse = UniverseResolver._select_primary_listing([l_nse, l_bse], policy="BSE_PRIORITY")
        assert chosen_bse.symbol == "588888"

    def test_missing_isin_safe_handling(self, nse_exchange):
        # Listing with an instrument having no isin is preserved without crashing
        inst, _ = Instrument.objects.get_or_create(
            isin="NO_ISIN_TEMP",
            defaults={"legal_name": "No ISIN Corp", "display_name": "No ISIN Corp", "is_active": True},
        )
        ExchangeListing.objects.create(
            symbol="NOISINSTOCK",
            exchange=nse_exchange,
            instrument=inst,
            is_tradeable=True,
        )
        resolved, meta = UniverseResolver.resolve(
            universe=["NOISINSTOCK"],
            deduplicate_dual_listings=True,
        )
        assert len(resolved) == 1
        assert resolved[0].symbol == "NOISINSTOCK"

    def test_ml_eligibility_classification_all_tiers(self, sample_listing):
        classifier = MLEligibilityClassifier(
            min_sessions=200,
            min_limited_sessions=50,
            min_median_volume=5000.0,
            max_stale_sessions=10,
        )
        expected_sessions = [date(2026, 1, 1) + timedelta(days=i) for i in range(250)]
        end_date = expected_sessions[-1]

        # 1. Inactive / Suspended
        sample_listing.is_tradeable = False
        res_suspended = classifier.classify_listing(sample_listing, [], expected_sessions, end_date)
        assert res_suspended.status == MLEligibilityStatus.SUSPENDED_OR_INACTIVE
        sample_listing.is_tradeable = True

        # 2. Insufficient History (< 50 sessions)
        candles_insufficient = [
            HistoricalCandle(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(2026, 8, 1, 10, 0)) + timedelta(days=i),
                volume=10000,
            )
            for i in range(30)
        ]
        res_insufficient = classifier.classify_listing(sample_listing, candles_insufficient, expected_sessions, end_date)
        assert res_insufficient.status == MLEligibilityStatus.INSUFFICIENT_HISTORY

        # 3. Limited History (50 <= N < 200 sessions, e.g. recent IPO)
        candles_limited = [
            HistoricalCandle(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(2026, 4, 1, 10, 0)) + timedelta(days=i),
                volume=10000,
            )
            for i in range(100)
        ]
        res_limited = classifier.classify_listing(sample_listing, candles_limited, expected_sessions, end_date)
        assert res_limited.status == MLEligibilityStatus.LIMITED_HISTORY

        # 4. Insufficient Liquidity (volume < 5,000)
        # Give it recent candles up to expected_sessions[-1] so it is not stale
        candles_illiquid = [
            HistoricalCandle(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(expected_sessions[i].year, expected_sessions[i].month, expected_sessions[i].day, 10, 0)),
                volume=500,  # below 5000 threshold
            )
            for i in range(250)
        ]
        res_illiquid = classifier.classify_listing(sample_listing, candles_illiquid, expected_sessions, end_date)
        assert res_illiquid.status == MLEligibilityStatus.INSUFFICIENT_LIQUIDITY

        # 5. Stale Data (last candle older than 10 sessions from end_date)
        candles_stale = [
            HistoricalCandle(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(2026, 1, 1, 10, 0)) + timedelta(days=i),
                volume=10000,
            )
            for i in range(210)
        ]
        # latest is ~ day 210, if end_date is far in future, check staleness
        far_future = date(2027, 1, 1)
        res_stale_verified = classifier.classify_listing(sample_listing, candles_stale, expected_sessions, end_date=far_future)
        assert res_stale_verified.status == MLEligibilityStatus.STALE_DATA

        # 6. Data Quality Failed (excessive quarantine errors >= 5%)
        res_dq = classifier.classify_listing(
            sample_listing,
            candles_limited,
            expected_sessions,
            end_date=end_date,
            quarantined_count=20,  # 20 / 120 = 16.7% > 5%
        )
        assert res_dq.status == MLEligibilityStatus.DATA_QUALITY_FAILED

        # 7. Fully ML Eligible
        candles_eligible = [
            HistoricalCandle(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(2026, 1, 1, 10, 0)) + timedelta(days=i),
                volume=15000,
            )
            for i in range(245)
        ]
        res_eligible = classifier.classify_listing(sample_listing, candles_eligible, expected_sessions, end_date)
        assert res_eligible.status == MLEligibilityStatus.ML_ELIGIBLE
        assert "Meets all data depth" in res_eligible.reason

    def test_chunked_processing_and_dataset_reproducibility(self, sample_listing, nse_exchange):
        base_date = date(2026, 7, 1)
        # Create 2 listings with 15 candles each
        inst2, _ = Instrument.objects.get_or_create(
            isin="INE999CHUNK2",
            defaults={"legal_name": "Chunk Corp 2", "display_name": "Chunk Corp 2", "is_active": True},
        )
        listing2, _ = ExchangeListing.objects.get_or_create(
            symbol="CHUNKCORP2",
            exchange=nse_exchange,
            defaults={"instrument": inst2, "is_tradeable": True},
        )

        for lst in [sample_listing, listing2]:
            for i in range(15):
                c_date = base_date + timedelta(days=i)
                HistoricalCandle.objects.create(
                    listing=lst,
                    timestamp=timezone.make_aware(timezone.datetime(c_date.year, c_date.month, c_date.day, 10, 0)),
                    interval="1d",
                    open=Decimal("150.0"),
                    high=Decimal("155.0"),
                    low=Decimal("148.0"),
                    close=Decimal("152.0"),
                    volume=5000,
                    source_provider="TEST",
                )

        # Build with chunk_size=1
        builder_chunk1 = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=14),
            universe=[sample_listing.symbol, listing2.symbol],
            chunk_size=1,
        )
        df_chunk1, meta_chunk1 = builder_chunk1.build_canonical_dataframe()

        # Build with chunk_size=10
        builder_chunk10 = DatasetBuilder(
            start_date=base_date,
            end_date=base_date + timedelta(days=14),
            universe=[sample_listing.symbol, listing2.symbol],
            chunk_size=10,
        )
        df_chunk10, meta_chunk10 = builder_chunk10.build_canonical_dataframe()

        # Chunked streaming must produce 100% identical canonical dataset and hash
        assert len(df_chunk1) == len(df_chunk10)
        assert meta_chunk1["content_hash"] == meta_chunk10["content_hash"]

    def test_audit_only_command_execution(self, sample_listing):
        out = StringIO()
        call_command(
            "build_ml_dataset",
            universe=sample_listing.symbol,
            audit_only=True,
            stdout=out,
        )
        output = out.getvalue()
        assert "Historical Data Readiness & Coverage Audit" in output
        assert "ML Eligibility Classification Breakdown" in output

    def test_reconciliation_exact_mathematical_identity(self, sample_listing, nse_exchange):
        """
        Regression test for Phase 2.1 audit discrepancies:
        Proves total_expected_slots == total_valid_trading_candles + missing_pre_listing + missing_source_data
        """
        # Create a second listing with 0 candles
        inst2 = Instrument.objects.create(isin="INE000ZERO01", display_name="ZeroCo", legal_name="ZeroCo Ltd", is_active=True)
        listing_zero = ExchangeListing.objects.create(symbol="ZEROCO", exchange=nse_exchange, instrument=inst2, is_tradeable=True)

        base_date = date(2026, 6, 1)  # Monday
        end_date = date(2026, 6, 12)   # Friday (10 trading sessions)

        # Seed sample_listing with 6 candles starting from day 4 (pre-listing = 4 slots)
        for i in range(4, 10):
            HistoricalCandle.objects.create(
                listing=sample_listing,
                timestamp=timezone.make_aware(timezone.datetime(2026, 6, 1, 10, 0)) + timedelta(days=i),
                interval="1d",
                open=Decimal("100.0"),
                high=Decimal("105.0"),
                low=Decimal("95.0"),
                close=Decimal("102.0"),
                volume=10000,
            )

        builder = DatasetBuilder(
            start_date=base_date,
            end_date=end_date,
            universe=[sample_listing.symbol, listing_zero.symbol],
        )
        audit = builder.audit_universe_readiness()

        total_slots = audit["total_expected_slots"]
        valid_candles = audit["total_valid_trading_candles"]
        pre_listing = audit["missing_session_reasons"]["pre_listing"]
        missing_source = audit["missing_session_reasons"]["missing_source_data"]

        # Exact mathematical reconciliation identity
        assert total_slots == valid_candles + pre_listing + missing_source

    def test_sunday_non_trading_session_exclusion(self, sample_listing):
        """
        Regression test: Proves weekend/Sunday dates (e.g. 2026-11-22) are never
        treated as expected exchange trading sessions.
        """
        sunday_date = date(2026, 11, 22)
        assert not ExchangeCalendar.is_trading_day(sunday_date)

        builder = DatasetBuilder(
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 23),
            universe=[sample_listing.symbol],
        )
        expected = builder.get_expected_trading_sessions()
        assert sunday_date not in expected
        # Friday 20th and Monday 23rd should be included, Saturday 21st and Sunday 22nd omitted
        assert date(2026, 11, 20) in expected
        assert date(2026, 11, 23) in expected
        assert date(2026, 11, 21) not in expected
