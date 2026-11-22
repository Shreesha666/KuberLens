"""
Management Command to Ingest the Official NIFTY 500 and Full NSE Equities Universe.
Downloads official master directories directly from NSE India archives and provisions
canonical Instruments and ExchangeListings.
"""
import csv
import logging
import urllib.request
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.instruments.models import Exchange, ExchangeListing, Instrument

logger = logging.getLogger(__name__)

NSE_EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
NIFTY_500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"


class Command(BaseCommand):
    help = "Ingests official NIFTY 500 and full NSE Equities Universe from NSE India archives."

    def add_arguments(self, parser):
        parser.add_argument(
            "--nifty500",
            action="store_true",
            help="Ingest all 500 NIFTY 500 constituents with accurate industry classifications.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Ingest the entire NSE universe (~2,600+ actively listed equities).",
        )

    def handle(self, *args: Any, **options: Any):
        ingest_nifty500 = options.get("nifty500")
        ingest_all = options.get("all")

        # Default to both if neither explicitly passed
        if not ingest_nifty500 and not ingest_all:
            ingest_nifty500 = True
            ingest_all = True

        nse_exchange, _ = Exchange.objects.get_or_create(
            code="NSE",
            defaults={"name": "National Stock Exchange", "country": "India", "currency": "INR"}
        )

        if ingest_nifty500:
            self.stdout.write("Fetching official NIFTY 500 directory from NSE India...")
            self._ingest_nifty_500(nse_exchange)

        if ingest_all:
            self.stdout.write("Fetching complete equity master list (EQUITY_L.csv) from NSE India...")
            self._ingest_all_nse(nse_exchange)

        total_inst = Instrument.objects.count()
        total_listings = ExchangeListing.objects.filter(exchange=nse_exchange, is_tradeable=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone! Universe successfully expanded to {total_listings} active NSE listings ({total_inst} instruments)."
            )
        )

    def _ingest_nifty_500(self, nse_exchange: Exchange):
        req = urllib.request.Request(NIFTY_500_URL, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch NIFTY 500 CSV: {e}"))
            return

        reader = csv.DictReader(content.splitlines())
        rows = list(reader)
        self.stdout.write(f"Processing {len(rows)} NIFTY 500 constituents...")

        created_inst = 0
        created_list = 0

        for idx, row in enumerate(rows):
            sym = row.get("Symbol", "").strip().upper()
            name = row.get("Company Name", "").strip()
            industry = row.get("Industry", "").strip()
            isin = row.get("ISIN Code", "").strip()
            series = row.get("Series", "EQ").strip()

            if not sym or not isin:
                continue

            # Assign market cap based on index rank
            if idx < 100:
                cap_cat = "LARGE"
            elif idx < 250:
                cap_cat = "MID"
            else:
                cap_cat = "SMALL"

            disp_name = name.replace(" Limited", "").replace(" Ltd.", "").strip()

            inst, i_created = Instrument.objects.update_or_create(
                isin=isin,
                defaults={
                    "legal_name": name[:255],
                    "display_name": disp_name[:150],
                    "sector": industry[:100],
                    "industry": industry[:100],
                    "market_cap_category": cap_cat,
                    "is_active": True,
                }
            )
            if i_created:
                created_inst += 1

            _, l_created = ExchangeListing.objects.update_or_create(
                exchange=nse_exchange,
                symbol=sym,
                defaults={
                    "instrument": inst,
                    "trading_symbol": f"{sym}-{series}",
                    "series_or_group": series,
                    "is_primary": True,
                    "is_tradeable": True,
                }
            )
            if l_created:
                created_list += 1

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ NIFTY 500 Ingested: {created_list} new listings, {created_inst} new instruments.")
        )

    def _ingest_all_nse(self, nse_exchange: Exchange):
        req = urllib.request.Request(NSE_EQUITY_L_URL, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read().decode("utf-8")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to fetch NSE EQUITY_L.csv: {e}"))
            return

        reader = csv.DictReader(content.splitlines())
        # Strip header keys of whitespace
        rows = []
        for r in reader:
            clean_row = {k.strip(): v.strip() for k, v in r.items() if k}
            rows.append(clean_row)

        self.stdout.write(f"Processing {len(rows)} total listed NSE securities...")

        created_inst = 0
        created_list = 0

        for row in rows:
            sym = row.get("SYMBOL", "").strip().upper()
            name = row.get("NAME OF COMPANY", "").strip()
            isin = row.get("ISIN NUMBER", "").strip()
            series = row.get("SERIES", "EQ").strip()

            # Filter for standard equity series (EQ, BE, SM for SME)
            if not sym or not isin or series not in ["EQ", "BE", "SM", "BZ"]:
                continue

            disp_name = name.replace(" Limited", "").replace(" Ltd.", "").strip()

            inst, i_created = Instrument.objects.get_or_create(
                isin=isin,
                defaults={
                    "legal_name": name[:255],
                    "display_name": disp_name[:150],
                    "sector": "General",
                    "industry": "Equities",
                    "market_cap_category": "SMALL",
                    "is_active": True,
                }
            )
            if i_created:
                created_inst += 1

            _, l_created = ExchangeListing.objects.get_or_create(
                exchange=nse_exchange,
                symbol=sym,
                defaults={
                    "instrument": inst,
                    "trading_symbol": f"{sym}-{series}",
                    "series_or_group": series,
                    "is_primary": True,
                    "is_tradeable": True,
                }
            )
            if l_created:
                created_list += 1

        self.stdout.write(
            self.style.SUCCESS(f"  ✓ Full NSE Universe Ingested: {created_list} new listings, {created_inst} new instruments.")
        )
