"""
Automated Integration and Acceptance Tests: EOD Data Ingestion, Shadow Scheduler Integration & Data Readiness Hardening.
Complies with AIML Architecture v2.1 Section 18 Master Specification.
"""
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle
from apps.ml_engine.models import (
    MLShadowEvaluationRecord,
    MLShadowPipelineRun,
    PipelineHealthState,
)
from integrations.market_data.base import HistoricalCandleDTO
from integrations.market_data.exceptions import ProviderConnectionError
from services.calendar.exchange_calendar import ExchangeCalendar
from services.market_data.eod_service import (
    BENCHMARK_SYMBOL,
    PILOT_SYMBOLS,
    EODIngestionService,
)
from services.ml.shadow_service import ShadowEvaluationService


@pytest.fixture
def pilot_environment(db):
    """Provisions minimal pilot exchange listings for testing."""
    nse, _ = Exchange.objects.get_or_create(
        code="NSE",
        defaults={"name": "National Stock Exchange of India"},
    )
    # Benchmark
    b_inst, _ = Instrument.objects.get_or_create(
        isin="IN_INDEX_NIFTY50",
        defaults={
            "display_name": "NIFTY 50",
            "legal_name": "NIFTY 50 Benchmark Index",
            "sector": "INDEX",
            "industry": "BENCHMARK",
            "market_cap_category": "INDEX",
            "is_active": True,
        },
    )
    b_listing, _ = ExchangeListing.objects.get_or_create(
        exchange=nse,
        symbol=BENCHMARK_SYMBOL,
        defaults={
            "instrument": b_inst,
            "trading_symbol": "NIFTY 50",
            "series_or_group": "INDEX",
            "is_primary": True,
            "is_tradeable": False,
        },
    )

    # Pilot Equities
    listings = [b_listing]
    for sym in PILOT_SYMBOLS:
        inst, _ = Instrument.objects.get_or_create(
            isin=f"INE_TEST_{sym}",
            defaults={
                "display_name": sym,
                "legal_name": f"{sym} Limited",
                "sector": "Technology" if "INFY" in sym or "TCS" in sym else "General",
                "industry": "Diversified",
                "market_cap_category": "LARGE",
                "is_active": True,
            },
        )
        lst, _ = ExchangeListing.objects.get_or_create(
            exchange=nse,
            symbol=sym,
            defaults={
                "instrument": inst,
                "trading_symbol": f"{sym}-EQ",
                "series_or_group": "EQ",
                "is_primary": True,
                "is_tradeable": True,
            },
        )
        listings.append(lst)

    return {"exchange": nse, "benchmark": b_listing, "listings": listings}


@pytest.mark.django_db
def test_eod_ingestion_holiday_skip():
    """Verify EOD ingestion cleanly skips official exchange holidays (e.g. Guru Nanak Jayanti 2026-11-24)."""
    holiday_date = date(2026, 11, 24)
    assert not ExchangeCalendar.is_trading_day(holiday_date)

    res = EODIngestionService.ingest_session_eod(session_date=holiday_date)
    assert res["status"] == "SKIPPED_HOLIDAY"
    assert res["is_trading_day"] is False
    assert "Guru Nanak Jayanti" in res["holiday_reason"]
    assert res["candles_ingested"] == 0
    assert len(res["errors"]) == 0


@pytest.mark.django_db
def test_strict_data_readiness_gate_missing_candles_rejection():
    """Verify validate_session_readiness rejects sessions with zero candles even under --force."""
    svc = ShadowEvaluationService()
    test_session = date(2026, 11, 23)

    # Ensure 0 candles exist for 2026-11-23
    HistoricalCandle.objects.filter(timestamp__date=test_session).delete()

    # Normal validation
    res_normal = svc.validate_session_readiness(test_session, required_symbols=PILOT_SYMBOLS, force=False)
    assert res_normal["is_ready"] is False
    assert res_normal["candle_count"] == 0
    assert res_normal["status"] in ("WAITING_FOR_DATA", "FAILED")
    assert "No 1d historical candles found" in res_normal["reason"]

    # Forced validation MUST STILL FAIL when candle_count == 0!
    res_forced = svc.validate_session_readiness(test_session, required_symbols=PILOT_SYMBOLS, force=True)
    assert res_forced["is_ready"] is False
    assert res_forced["candle_count"] == 0
    assert res_forced["status"] in ("WAITING_FOR_DATA", "FAILED")


@pytest.mark.django_db
def test_strict_data_readiness_gate_missing_benchmark(pilot_environment):
    """Verify validate_session_readiness detects missing benchmark (^NSEI) and sets status DEGRADED."""
    svc = ShadowEvaluationService()
    test_session = date(2026, 11, 20)
    ist_tz = ExchangeCalendar.IST
    candle_ts = datetime.combine(test_session, datetime.min.time(), tzinfo=ist_tz).astimezone(UTC)

    # Populate equity candles but omit benchmark ^NSEI
    for sym in PILOT_SYMBOLS:
        lst = ExchangeListing.objects.filter(symbol=sym).first()
        HistoricalCandle.objects.update_or_create(
            listing=lst,
            timestamp=candle_ts,
            interval="1d",
            defaults={
                "open": Decimal("100.0"),
                "high": Decimal("105.0"),
                "low": Decimal("99.0"),
                "close": Decimal("103.0"),
                "volume": 10000,
                "source_provider": "YAHOO",
            },
        )

    # Ensure benchmark is deleted
    b_lst = ExchangeListing.objects.filter(symbol=BENCHMARK_SYMBOL).first()
    HistoricalCandle.objects.filter(listing=b_lst, timestamp__date=test_session).delete()

    res = svc.validate_session_readiness(test_session, required_symbols=PILOT_SYMBOLS, force=False)
    assert res["is_ready"] is False
    assert res["benchmark_available"] is False
    assert res["status"] == "DEGRADED"
    assert "Benchmark index candle (^NSEI) missing" in res["reason"]


@pytest.mark.django_db
def test_eod_ingestion_bounded_retry_and_dns_recovery(pilot_environment):
    """Verify bounded retries on network/DNS errors and zero synthetic data creation."""
    test_session = date(2026, 11, 23)

    mock_provider = MagicMock()
    mock_provider.get_historical_candles.side_effect = ProviderConnectionError(
        "DNS resolution failed: [Errno 8] nodename nor servname provided, or not known"
    )

    with patch("services.market_data.eod_service.ProviderRegistry.get", return_value=mock_provider):
        res = EODIngestionService.ingest_session_eod(
            session_date=test_session,
            universe=["RELIANCE"],
            max_retries=3,
            rate_limit_delay_seconds=0.01,
        )

    assert res["status"] in ("FAILED", "WAITING_FOR_DATA")
    assert res["symbols_succeeded"] == 0
    assert "RELIANCE" in res["missing_symbols"]
    assert len(res["errors"]) > 0
    assert "DNS resolution failed" in res["errors"][0]["error"]

    # Verify ZERO synthetic fallback candles were created
    created_candles = HistoricalCandle.objects.filter(timestamp__date=test_session).count()
    assert created_candles == 0


@pytest.mark.django_db
def test_eod_ingestion_successful_upsert(pilot_environment):
    """Verify successful ingestion and idempotent upsert into HistoricalCandle with retrieved_at timestamp."""
    test_session = date(2026, 11, 23)
    ist_tz = ExchangeCalendar.IST
    candle_ts = datetime.combine(test_session, datetime.min.time(), tzinfo=ist_tz).astimezone(UTC)

    def mock_get_candles(listing, start_date, end_date, interval="1d"):
        return [
            HistoricalCandleDTO(
                timestamp=candle_ts,
                interval=interval,
                open=Decimal("1500.00"),
                high=Decimal("1520.00"),
                low=Decimal("1490.00"),
                close=Decimal("1510.00"),
                volume=500000,
                adjusted_close=Decimal("1510.00"),
                source_provider="YAHOO",
            )
        ]

    mock_provider = MagicMock()
    mock_provider.get_historical_candles.side_effect = mock_get_candles

    with patch("services.market_data.eod_service.ProviderRegistry.get", return_value=mock_provider):
        res = EODIngestionService.ingest_session_eod(
            session_date=test_session,
            universe=["RELIANCE", "TCS"],
            max_retries=1,
            rate_limit_delay_seconds=0.0,
        )

    assert res["status"] == "SUCCESS"
    assert res["symbols_succeeded"] == 3  # RELIANCE + TCS + ^NSEI
    assert res["candles_ingested"] == 3

    # Check persistence in database
    reliance_candle = HistoricalCandle.objects.filter(listing__symbol="RELIANCE", timestamp__date=test_session).first()
    assert reliance_candle is not None
    assert reliance_candle.close == Decimal("1510.00")
    assert reliance_candle.source_provider == "YAHOO"
    assert reliance_candle.retrieved_at is not None


@pytest.mark.django_db
def test_november_23_regression_zero_features_not_false_success(pilot_environment):
    """
    Regression Test for November 23 failure:
    Sessions with 0 target-session candles must HALT and NOT be marked SUCCESS.
    """
    test_session = date(2026, 11, 23)
    # Ensure 0 candles exist on 2026-11-23
    HistoricalCandle.objects.filter(timestamp__date=test_session).delete()

    # Run the pipeline without force
    call_command(
        "run_shadow_eod_pipeline",
        session_date="2026-11-23",
        dry_run=False,
    )

    last_run = MLShadowPipelineRun.objects.filter(session_date=test_session).order_by("-started_at").first()
    assert last_run is not None
    assert last_run.status == "WAITING_FOR_DATA"
    assert last_run.health_state == PipelineHealthState.WAITING_FOR_DATA
    assert "No 1d historical candles found" in last_run.error_details

    # Verify no shadow evaluation records or false positives persisted
    assert MLShadowEvaluationRecord.objects.filter(session_date=test_session).count() == 0


@pytest.mark.django_db
def test_pipeline_health_state_reflects_waiting_for_data(pilot_environment):
    """Verify that get_pipeline_health_state reports WAITING_FOR_DATA and never OPERATIONAL when data is missing."""
    svc = ShadowEvaluationService()

    # Create run with WAITING_FOR_DATA
    MLShadowPipelineRun.objects.create(
        run_id=timezone.uuid.uuid4() if hasattr(timezone, "uuid") else "11111111-2222-3333-4444-555555555555",
        session_date=date(2026, 11, 23),
        status="WAITING_FOR_DATA",
        health_state=PipelineHealthState.WAITING_FOR_DATA,
        started_at=timezone.now(),
        error_details="Awaiting EOD market data ingestion.",
    )

    state = svc.get_pipeline_health_state()
    assert state["health_state"] == PipelineHealthState.WAITING_FOR_DATA.value
    assert state["scheduler_status"] == "WAITING_FOR_DATA"
    assert state["scheduler_status"] != "OPERATIONAL"


@pytest.mark.django_db
def test_legitimate_zero_candidate_session_marks_success(pilot_environment, monkeypatch):
    """
    Verify that when candles exist for all pilot symbols and features are calculated for all,
    but 0 candidate setups trigger, the pipeline marks status SUCCESS and HEALTHY.
    """
    from io import StringIO

    import pandas as pd

    from services.ml.dataset_builder import DatasetBuilder

    test_session = date(2026, 11, 20)
    ist_tz = ExchangeCalendar.IST
    candle_ts = datetime.combine(test_session, datetime.min.time(), tzinfo=ist_tz).astimezone(UTC)

    # 1. Populate Stage 1 HistoricalCandle records
    for lst in pilot_environment["listings"]:
        HistoricalCandle.objects.update_or_create(
            listing=lst,
            timestamp=candle_ts,
            interval="1d",
            defaults={
                "open": Decimal("100.0"),
                "high": Decimal("105.0"),
                "low": Decimal("99.0"),
                "close": Decimal("103.0"),
                "volume": 10000,
                "source_provider": "YAHOO",
            },
        )

    # 2. Build mock canonical DataFrame spanning up to 2026-11-20
    dates = [f"2026-11-{i:02d}" for i in range(1, 21)]
    rows = []
    for sym in PILOT_SYMBOLS:
        for i, d in enumerate(dates):
            rows.append({
                "symbol": sym,
                "session_date": d,
                "open_raw": 100.0 + i,
                "high_raw": 102.0 + i,
                "low_raw": 99.0 + i,
                "close_raw": 101.0 + i,
                "volume_raw": 500_000,
                "open_adj": 100.0 + i,
                "high_adj": 102.0 + i,
                "low_adj": 99.0 + i,
                "close_adj": 101.0 + i,
                "volume_adj": 500_000.0,
                "benchmark_close_raw": 24000.0 + i,
                "benchmark_close_adj": 24000.0 + i,
            })
    df_canonical_mock = pd.DataFrame(rows)
    monkeypatch.setattr(DatasetBuilder, "build_canonical_dataframe", lambda self: (df_canonical_mock, {}))

    # 3. Execute pipeline
    out = StringIO()
    call_command(
        "run_shadow_eod_pipeline",
        session_date="2026-11-20",
        force=True,  # Session in past
        dry_run=False,
        stdout=out,
    )

    last_run = MLShadowPipelineRun.objects.filter(session_date=test_session).order_by("-started_at").first()
    assert last_run is not None
    assert last_run.status == "SUCCESS"
    assert last_run.health_state == PipelineHealthState.HEALTHY
    assert last_run.records_created == 0


@pytest.mark.django_db
def test_catchup_missed_respects_data_readiness_gate(pilot_environment):
    """Verify --catchup-missed does not falsely mark un-ingested missed sessions as SUCCESS."""
    test_session = date(2026, 11, 23)
    HistoricalCandle.objects.filter(timestamp__date=test_session).delete()

    # Run catchup missed
    call_command(
        "run_shadow_eod_pipeline",
        catchup_missed=True,
        dry_run=False,
    )

    run = MLShadowPipelineRun.objects.filter(session_date=test_session).order_by("-started_at").first()
    assert run is not None
    # Must NOT be SUCCESS
    assert run.status in ("WAITING_FOR_DATA", "FAILED")
    assert run.status != "SUCCESS"


@pytest.mark.django_db
def test_ingest_eod_data_cli_holiday():
    """Verify ingest_eod_data CLI cleanly exits with code 0 on holiday."""
    # Should not raise CommandError on holiday
    call_command("ingest_eod_data", session_date="2026-11-24")


@pytest.mark.django_db
def test_runner_script_syntax_and_steps():
    """Verify that scripts/run_shadow_eod_cron.sh includes ingest_eod_data and --ingest-eod."""
    from pathlib import Path

    script_path = Path(__file__).resolve().parent.parent / "scripts" / "run_shadow_eod_cron.sh"
    assert script_path.exists()

    content = script_path.read_text()
    assert "ingest_eod_data" in content
    assert "--ingest-eod" in content
    assert "--catchup-missed" in content
