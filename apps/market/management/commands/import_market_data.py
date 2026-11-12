"""
Management command to import or update market quotes and historical candles.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.instruments.models import ExchangeListing
from services.market_data.service import MarketDataService


class Command(BaseCommand):
    help = "Imports market quotes or historical candles for exchange listings."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", type=str, help="Specific trading symbol (e.g. RELIANCE)")
        parser.add_argument("--exchange", type=str, default="NSE", help="Exchange code (default: NSE)")
        parser.add_argument("--history", action="store_true", help="Fetch historical candles instead of quotes")
        parser.add_argument("--days", type=int, default=30, help="Number of historical days to fetch (default: 30)")
        parser.add_argument("--interval", type=str, default="1d", help="Candle interval (default: 1d)")
        parser.add_argument("--all", action="store_true", help="Fetch for all active listings")

    def handle(self, *args, **options):
        symbol = options.get("symbol")
        exchange_code = options.get("exchange", "NSE")
        history = options.get("history", False)
        days = options.get("days", 30)
        interval = options.get("interval", "1d")
        fetch_all = options.get("all", False)

        if not symbol and not fetch_all:
            raise CommandError("Please specify --symbol or --all.")

        listings = ExchangeListing.objects.filter(is_tradeable=True, exchange__code=exchange_code)
        if symbol:
            listings = listings.filter(symbol=symbol.upper())

        if not listings.exists():
            self.stdout.write(self.style.WARNING(f"No active listings found for symbol={symbol}, exchange={exchange_code}"))
            return

        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)

        self.stdout.write(
            f"Processing {listings.count()} listings (Mode: {'Historical ' + interval if history else 'Quote'})..."
        )

        success_count = 0
        error_count = 0

        for listing in listings:
            try:
                if history:
                    candles = MarketDataService.get_historical_candles(
                        listing=listing,
                        start_date=start_date,
                        end_date=end_date,
                        interval=interval,
                        fetch_if_missing=True,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"[{listing.symbol}] Synced {len(candles)} candles ({start_date} to {end_date})")
                    )
                else:
                    quote = MarketDataService.get_quote(listing=listing, force_refresh=True)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[{listing.symbol}] Price: ₹{quote.price} | Provider: {quote.source_provider} | "
                            f"Status: {quote.freshness_status} ({quote.source_type})"
                        )
                    )
                success_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"[{listing.symbol}] Failed: {e}"))
                error_count += 1

        self.stdout.write(
            self.style.NOTICE(f"Finished. Success: {success_count}, Errors: {error_count}")
        )
