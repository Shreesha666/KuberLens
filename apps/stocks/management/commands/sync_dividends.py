import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
from django.db import connection
from apps.instruments.models import ExchangeListing
from services.fundamentals.analyzer import FundamentalAnalyzer

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Syncs real corporate dividend rates (DPS in ₹) and dividend yields (%) from Yahoo Finance."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbol",
            type=str,
            help="Specific stock symbol to sync (e.g. COALINDIA, ABB, ITC).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Sync dividends for all primary tradeable listings.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Limit number of listings to sync when running batch.",
        )
        parser.add_argument(
            "--workers",
            type=int,
            default=8,
            help="Number of concurrent worker threads (default: 8).",
        )

    def handle(self, *args, **options):
        symbol = options.get("symbol")
        sync_all = options.get("all")
        limit = options.get("limit")
        workers = options.get("workers", 8)

        if symbol:
            listings = list(ExchangeListing.objects.filter(symbol=symbol.upper(), is_primary=True))
            if not listings:
                self.stdout.write(self.style.ERROR(f"Listing '{symbol}' not found."))
                return
        elif sync_all:
            listings = list(ExchangeListing.objects.filter(is_primary=True, is_tradeable=True))
        else:
            listings = list(ExchangeListing.objects.filter(is_primary=True, is_tradeable=True)[:limit])

        total = len(listings)
        self.stdout.write(f"Syncing real Yahoo Finance dividends for {total} instrument(s) using {workers} workers...")

        def _sync_one(listing):
            try:
                rate, yd = FundamentalAnalyzer.sync_dividend_from_yahoo(
                    symbol=listing.symbol, instrument=listing.instrument
                )
                return listing.symbol, rate, yd, None
            except Exception as e:
                return listing.symbol, None, None, str(e)
            finally:
                connection.close()

        synced = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_sym = {executor.submit(_sync_one, l): l.symbol for l in listings}
            for future in as_completed(future_to_sym):
                sym, rate, yd, err = future.result()
                if err:
                    self.stdout.write(self.style.ERROR(f"  ✗ {sym}: {err}"))
                elif rate is not None or yd is not None:
                    synced += 1
                    rate_str = f"₹{rate:.2f}" if rate is not None else "₹0.00"
                    yd_str = f"{yd:.2f}%" if yd is not None else "0.00%"
                    self.stdout.write(self.style.SUCCESS(f"  ✓ {sym}: DPS {rate_str} | Yield {yd_str}"))
                else:
                    self.stdout.write(self.style.WARNING(f"  - {sym}: No dividend record"))

        self.stdout.write(
            self.style.SUCCESS(f"\nDone! Successfully synced real corporate dividends for {synced}/{total} stocks.")
        )

