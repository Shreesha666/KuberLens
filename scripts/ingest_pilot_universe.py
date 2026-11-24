"""
Phase 3.3 Pilot Universe Historical Ingestion & Verification Script.
Ingests multi-year authentic market data for the pilot universe:
- Benchmark index (^NSEI)
- 9 NSE Bluechips
- 9 BSE Dual-listed scrips
- 4 Mid/Small caps
- 3 Recent IPOs
Target date range: 2020-01-01 to 2026-11-23.
"""
import os
import sys
from datetime import date
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import django  # noqa: E402

# Setup Django environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from apps.instruments.models import ExchangeListing  # noqa: E402
from apps.market.models import HistoricalCandle  # noqa: E402
from services.calendar.exchange_calendar import ExchangeCalendar  # noqa: E402
from services.market_data.historical_pipeline import HistoricalDataIngestionPipeline  # noqa: E402


def run_pilot_ingestion():
    print("=" * 80)
    print("KUBERLENS PHASE 3.3 — PILOT HISTORICAL DATA INGESTION & AUDIT")
    print("=" * 80)

    pipeline = HistoricalDataIngestionPipeline(
        provider_code="YAHOO",
        rate_limit_delay_seconds=0.5,
        max_retries=3,
        batch_size=10,
        verify_against_calendar=True,
        backfill_mode=True,
    )

    # 1. Register or retrieve benchmark listing
    benchmark = pipeline.register_or_get_benchmark_listing()
    print(f"Benchmark listing: {benchmark.symbol} (ISIN: {benchmark.instrument.isin}, Sector: {benchmark.instrument.sector})")

    # 2. Collect target listings
    nse_bluechips = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "LT", "ITC", "BHARTIARTL"]
    bse_dual_listed = ["500325", "532540", "500209", "500180", "500112", "500510", "500875", "532174", "532454"]
    mid_small = ["20MICRONS", "XPROINDIA", "PAYTM", "LODHA"]
    recent_ipos = ["SWIGGY", "OLAELEC", "NTPCGREEN"]

    listings = [benchmark]

    for sym in nse_bluechips:
        lst = ExchangeListing.objects.filter(exchange__code="NSE", symbol=sym).first()
        if lst:
            listings.append(lst)
        else:
            print(f"WARNING: NSE listing not found for {sym}")

    for sym in bse_dual_listed:
        lst = ExchangeListing.objects.filter(exchange__code="BSE", symbol=sym).first()
        if lst:
            listings.append(lst)
        else:
            print(f"WARNING: BSE listing not found for {sym}")

    for sym in mid_small:
        lst = ExchangeListing.objects.filter(exchange__code="NSE", symbol=sym).first()
        if lst:
            listings.append(lst)
        else:
            print(f"WARNING: Mid/Small listing not found for {sym}")

    for sym in recent_ipos:
        lst = ExchangeListing.objects.filter(exchange__code="NSE", symbol=sym).first()
        if lst:
            listings.append(lst)
        else:
            print(f"WARNING: IPO listing not found for {sym}")

    print(f"\nTotal pilot listings to ingest: {len(listings)}")
    for i, lst in enumerate(listings, 1):
        print(f"  {i:02d}. [{lst.exchange.code}] {lst.symbol} ({lst.trading_symbol}) - {lst.instrument.display_name}")

    # 3. Baseline candle counts
    initial_total = HistoricalCandle.objects.count()
    initial_pilot = HistoricalCandle.objects.filter(listing__in=listings).count()
    initial_auth = HistoricalCandle.objects.filter(listing__in=listings, source_provider="YAHOO").count()
    print("\nPre-ingestion DB status:")
    print(f"  Total candles across DB: {initial_total}")
    print(f"  Candles for pilot universe: {initial_pilot} (Authentic YAHOO: {initial_auth})")

    # 4. Execute ingestion
    start_date = date(2020, 1, 1)
    end_date = date(2026, 11, 23)

    print(f"\nStarting ingestion for period {start_date} to {end_date}...")
    summary = pipeline.ingest_universe(
        listings=listings,
        start_date=start_date,
        end_date=end_date,
        interval="1d",
        backfill_mode=True,
    )

    print("\nIngestion summary:")
    print(f"  Total processed: {summary['total_processed']}")
    print(f"  Success: {summary['success_count']}, Failed: {summary['failed_count']}")
    print(f"  Total candles ingested: {summary['total_candles_ingested']}")

    # 5. Data quality and calendar audit
    print("\n" + "=" * 80)
    print("DATA INTEGRITY & CALENDAR ALIGNMENT AUDIT")
    print("=" * 80)

    calendar_violations = 0
    ohlc_violations = 0
    total_audited = 0

    coverage_tiers = {"5y+": 0, "3y-5y": 0, "1y-3y": 0, "<1y": 0}
    tier_details = []

    for lst in listings:
        candles = list(HistoricalCandle.objects.filter(listing=lst, interval="1d", source_provider="YAHOO").order_by("timestamp"))
        count = len(candles)
        total_audited += count

        if count == 0:
            tier_details.append((lst.exchange.code, lst.symbol, 0, None, None, "<1y"))
            coverage_tiers["<1y"] += 1
            continue

        first_d = candles[0].timestamp.date()
        last_d = candles[-1].timestamp.date()
        days_span = (last_d - first_d).days
        years_span = round(days_span / 365.25, 2)

        tier = "<1y"
        if years_span >= 5.0:
            tier = "5y+"
            coverage_tiers["5y+"] += 1
        elif years_span >= 3.0:
            tier = "3y-5y"
            coverage_tiers["3y-5y"] += 1
        elif years_span >= 1.0:
            tier = "1y-3y"
            coverage_tiers["1y-3y"] += 1
        else:
            tier = "<1y"
            coverage_tiers["<1y"] += 1

        tier_details.append((lst.exchange.code, lst.symbol, count, first_d, last_d, tier))

        # Check calendar and OHLC bounds
        for c in candles:
            cdate = c.timestamp.date()
            if not ExchangeCalendar.is_trading_day(cdate):
                calendar_violations += 1
            if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high and c.volume >= 0):
                ohlc_violations += 1

    print(f"\nAudit results across {total_audited} ingested candles:")
    print(f"  Calendar violations (candles on weekends/holidays): {calendar_violations}")
    print(f"  OHLC bounds violations: {ohlc_violations}")

    # 6. Corporate action / raw vs adjusted price separation
    print("\nRaw vs Adjusted Close divergence audit (Corporate action awareness):")
    for lst in listings[:5]:
        sample = HistoricalCandle.objects.filter(listing=lst, interval="1d", source_provider="YAHOO").order_by("timestamp").first()
        if sample:
            diff = abs(sample.close - (sample.adjusted_close or sample.close))
            print(f"  [{lst.exchange.code}] {lst.symbol} ({sample.timestamp.date()}): Close={sample.close}, AdjClose={sample.adjusted_close}, Diff={diff}")

    # 7. Coverage tier breakdown
    print("\nCoverage Tier Breakdown:")
    for tier, cnt in coverage_tiers.items():
        print(f"  Tier {tier}: {cnt} listings")

    print("\nListing Details:")
    print(f"  {'Exchange':<8} {'Symbol':<12} {'Candles':<8} {'First Date':<12} {'Last Date':<12} {'Tier':<6}")
    print("  " + "-" * 62)
    for ex, sym, cnt, fd, ld, tr in tier_details:
        print(f"  {ex:<8} {sym:<12} {cnt:<8} {str(fd):<12} {str(ld):<12} {tr:<6}")

    print("\n" + "=" * 80)
    print("PILOT INGESTION & AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    run_pilot_ingestion()
