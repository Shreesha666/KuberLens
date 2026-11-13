"""
Django management command to sync live primary market data from ipos.markets.
Usage:
    python manage.py sync_ipo_data
    python manage.py sync_ipo_data --limit=30
    python manage.py sync_ipo_data --live-only
"""
from django.core.management.base import BaseCommand

from services.ipo.sync import sync_ipos_markets


class Command(BaseCommand):
    help = "Synchronizes Indian Primary Market IPO issues and subscription data from ipos.markets"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Maximum number of issues to fetch detail profiles for (default: 20)",
        )
        parser.add_argument(
            "--live-only",
            action="store_true",
            help="Only synchronize currently open and upcoming pipeline issues",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        live_only = options["live_only"]

        self.stdout.write(
            self.style.NOTICE(f"Connecting to ipos.markets (limit={limit}, live_only={live_only})...")
        )

        stats = sync_ipos_markets(live_only=live_only, detail_limit=limit)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync completed successfully! Created: {stats['created']}, "
                f"Updated: {stats['updated']}, Errors: {stats['errors']}"
            )
        )

