"""
Seeds system screener configurations and default user watchlists with tracking thresholds.
"""
import logging
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.screener.models import ScreenerConfiguration
from apps.watchlists.models import Watchlist, WatchlistItem
from services.screener.engine import SYSTEM_PRESETS

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Seeds system screener configurations and default user watchlists."

    def handle(self, *args, **options):
        self.stdout.write("Seeding system screener presets and default watchlists...")

        # 1. Seed System Screener Presets
        for slug, preset in SYSTEM_PRESETS.items():
            cfg, created = ScreenerConfiguration.objects.update_or_create(
                preset_slug=slug,
                defaults={
                    "name": preset["name"],
                    "description": preset["description"],
                    "filter_criteria": {k: str(v) if isinstance(v, Decimal) else v for k, v in preset["filters"].items()},
                    "is_system_preset": True,
                    "is_public": True,
                },
            )
            status = "Created" if created else "Updated"
            self.stdout.write(f"  {status} system screener preset: {cfg.name}")

        # 2. Seed Default User Watchlists
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            self.stdout.write(self.style.WARNING("No users found to seed watchlists for."))
            return

        wl_long, _ = Watchlist.objects.get_or_create(
            user=user,
            name="Core Long-Term Ideas",
            defaults={
                "description": "High-quality market leaders and steady dividend compounders.",
                "is_default": True,
            },
        )

        wl_swing, _ = Watchlist.objects.get_or_create(
            user=user,
            name="Swing & Momentum Setups",
            defaults={
                "description": "Short-to-medium term pullbacks and breakout triggers.",
                "is_default": False,
            },
        )

        # Populate stocks in Core Long-Term
        for sym, target, stop, note in [
            ("RELIANCE", Decimal("3300.00"), Decimal("2700.00"), "Energy transition & retail expansion"),
            ("TCS", Decimal("4500.00"), Decimal("3800.00"), "IT sector leader with high ROE"),
            ("HDFCBANK", Decimal("1950.00"), Decimal("1580.00"), "Private banking core franchise"),
        ]:
            listing = ExchangeListing.objects.filter(symbol=sym).first()
            if listing:
                quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
                added_p = quote.price if quote else Decimal("1000.00")
                WatchlistItem.objects.update_or_create(
                    watchlist=wl_long,
                    listing=listing,
                    defaults={
                        "added_price": added_p,
                        "target_price": target,
                        "stop_loss": stop,
                        "notes": note,
                    },
                )
                self.stdout.write(f"  Added {sym} to '{wl_long.name}'")

        # Populate stocks in Swing Setups
        for sym, target, stop, note in [
            ("BANKINDIA", Decimal("175.00"), Decimal("140.00"), "PSU banking rally momentum"),
            ("MOREPENLAB", Decimal("115.00"), Decimal("88.00"), "Pharma breakout candidate"),
            ("NRBBEARING", Decimal("480.00"), Decimal("410.00"), "Auto ancillary cyclical demand"),
        ]:
            listing = ExchangeListing.objects.filter(symbol=sym).first()
            if listing:
                quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
                added_p = quote.price if quote else Decimal("100.00")
                WatchlistItem.objects.update_or_create(
                    watchlist=wl_swing,
                    listing=listing,
                    defaults={
                        "added_price": added_p,
                        "target_price": target,
                        "stop_loss": stop,
                        "notes": note,
                    },
                )
                self.stdout.write(f"  Added {sym} to '{wl_swing.name}'")

        self.stdout.write(self.style.SUCCESS("Screener presets and watchlists successfully seeded."))
