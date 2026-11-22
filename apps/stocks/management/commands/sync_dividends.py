import logging
from django.core.management.base import BaseCommand
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

    def handle(self, *args, **options):
        symbol = options.get("symbol")
        sync_all = options.get("all")
        limit = options.get("limit")

        if symbol:
            listings = ExchangeListing.objects.filter(symbol=symbol.upper(), is_primary=True)
            if not listings.exists():
                self.stdout.write(self.style.ERROR(f"Listing '{symbol}' not found."))
                return
        elif sync_all:
            listings = ExchangeListing.objects.filter(is_primary=True, is_tradeable=True)
        else:
            # Sync top holdings / watchlist / popular stocks first
            listings = ExchangeListing.objects.filter(is_primary=True, is_tradeable=True)[:limit]

        synced = 0
        total = listings.count()
        self.stdout.write(f"Syncing real Yahoo Finance dividends for {total} instrument(s)...")

        for listing in listings:
            try:
                rate, yd = FundamentalAnalyzer.sync_dividend_from_yahoo(
                    symbol=listing.symbol, instrument=listing.instrument
                )
                if rate is not None or yd is not None:
                    synced += 1
                    rate_str = f"₹{rate:.2f}" if rate is not None else "—"
                    yd_str = f"{yd:.2f}%" if yd is not None else "—"
                    self.stdout.write(
                        self.style.SUCCESS(f"  ✓ {listing.symbol}: DPS {rate_str} | Yield {yd_str}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  - {listing.symbol}: No dividend payout on Yahoo Finance")
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ {listing.symbol}: Failed to sync: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"\nDone! Successfully synced dividends for {synced}/{total} stocks.")
        )
