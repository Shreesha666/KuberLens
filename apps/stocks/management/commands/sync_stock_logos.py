"""
Management command to batch synchronize and locally persist company stock logos.
Downloads official vector SVGs into static/branding/stock_logos/ with multithreading
and generates high-DPI monogram fallbacks for instant (< 1ms) zero-latency rendering.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from pathlib import Path
import time

from django.core.management.base import BaseCommand

from apps.instruments.models import ExchangeListing
from services.logos import CompanyLogoService


class Command(BaseCommand):
    help = "Downloads and permanently caches vector stock logos to local disk for 0-latency offline rendering."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-download and overwrite existing local logo files.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=8,
            help="Number of concurrent worker threads for downloading (default: 8).",
        )
        parser.add_argument(
            "--symbols",
            type=str,
            default="",
            help="Optional comma-separated list of symbols to sync (e.g. RELIANCE,TCS,INFY).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        concurrency = options["concurrency"]
        symbols_arg = options["symbols"]

        logo_dir = CompanyLogoService.get_local_storage_dir()

        if symbols_arg:
            symbols = [s.strip().upper() for s in symbols_arg.split(",") if s.strip()]
        else:
            symbols = list(
                ExchangeListing.objects.values_list("symbol", flat=True)
                .order_by("symbol")
                .distinct()
            )

        total_count = len(symbols)
        if total_count == 0:
            self.stdout.write(self.style.WARNING("No stock listings found in the database."))
            return

        self.stdout.write(
            self.style.NOTICE(
                f"Starting logo synchronization for {total_count} stocks using {concurrency} threads..."
            )
        )
        self.stdout.write(f"Target directory: {logo_dir}")

        start_time = time.time()
        official_downloaded = 0
        monograms_generated = 0
        already_cached = 0
        errors = 0

        def process_symbol(symbol: str) -> tuple[str, str]:
            svg_path = logo_dir / f"{symbol}.svg"
            png_path = logo_dir / f"{symbol}.png"

            # Check if already present and not forcing overwrite
            if not force and (svg_path.is_file() or png_path.is_file()):
                return symbol, "cached"

            # Attempt remote fetch
            content, content_type = CompanyLogoService.fetch_remote_logo(symbol, timeout=2.5)
            if content:
                ext = "png" if "png" in content_type else "svg"
                target_path = logo_dir / f"{symbol}.{ext}"
                target_path.write_bytes(content)
                return symbol, "downloaded"

            # Fallback monogram
            monogram = CompanyLogoService.generate_fallback_monogram(symbol)
            svg_path.write_bytes(monogram)
            return symbol, "monogram"

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            future_to_symbol = {
                executor.submit(process_symbol, sym): sym for sym in symbols
            }

            completed = 0
            for future in as_completed(future_to_symbol):
                completed += 1
                sym = future_to_symbol[future]
                try:
                    _, status = future.result()
                    if status == "downloaded":
                        official_downloaded += 1
                    elif status == "monogram":
                        monograms_generated += 1
                    elif status == "cached":
                        already_cached += 1
                except Exception as exc:
                    errors += 1
                    self.stdout.write(self.style.ERROR(f"Error processing {sym}: {exc}"))

                if completed % 25 == 0 or completed == total_count:
                    pct = (completed / total_count) * 100
                    self.stdout.write(f"Progress: {completed}/{total_count} ({pct:.1f}%)")

        elapsed = time.time() - start_time

        # Calculate total storage used in logo_dir
        total_size_bytes = sum(
            f.stat().st_size for f in logo_dir.glob("*") if f.is_file()
        )
        total_size_kb = total_size_bytes / 1024
        total_size_mb = total_size_kb / 1024

        self.stdout.write(self.style.SUCCESS("\nLogo Synchronization Complete!"))
        self.stdout.write(f"&bull; Total Stocks Processed: {total_count}")
        self.stdout.write(f"&bull; Official Vector Logos Downloaded: {official_downloaded}")
        self.stdout.write(f"&bull; Clean SVG Monograms Generated: {monograms_generated}")
        self.stdout.write(f"&bull; Already Local / Unchanged: {already_cached}")
        if errors > 0:
            self.stdout.write(f"&bull; Errors: {errors}")
        self.stdout.write(f"&bull; Total Disk Storage: {total_size_kb:.1f} KB ({total_size_mb:.2f} MB)")
        self.stdout.write(f"&bull; Total Execution Time: {elapsed:.2f} seconds")

