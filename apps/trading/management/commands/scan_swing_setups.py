"""
Management command to scan the tradeable universe and persist qualified swing setups.
"""
from django.core.management.base import BaseCommand

from services.trading.scanner import SwingScanner


class Command(BaseCommand):
    help = "Scans the exchange universe for 1-8 week swing trade setups and stores active setups."

    def add_arguments(self, parser):
        parser.add_argument("--strategy", type=str, default="ALL", help="Filter by specific strategy code")
        parser.add_argument("--cap", type=str, default="ALL", help="Filter by market cap (LARGE, MID, ALL)")
        parser.add_argument("--min-rr", type=float, default=1.5, help="Minimum Risk/Reward ratio (default 1.5)")

    def handle(self, *args, **options):
        strat = options.get("strategy")
        cap = options.get("cap")
        min_rr = options.get("min_rr")

        self.stdout.write(f"Scanning market universe (strategy={strat}, cap={cap}, min_rr={min_rr})...")
        setups = SwingScanner.scan_universe(
            strategy_filter=strat,
            market_cap_filter=cap,
            min_rr=min_rr,
            save_setups=True,
        )

        self.stdout.write(self.style.SUCCESS(f"Successfully identified and updated {len(setups)} qualified swing setups!"))
        for s in setups[:10]:
            self.stdout.write(
                f" - [{s['symbol']}] {s['strategy_name']} | Price: ₹{s['current_price']:.2f} | "
                f"SL: ₹{s['stop_loss']:.2f} | T1: ₹{s['target_1']:.2f} | R:R 1:{s['risk_reward']}"
            )
