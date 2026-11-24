#!/usr/bin/env python3
"""
KuberLens Documentation Screenshot Generator
Automates capturing high-resolution desktop screenshots of every KuberLens page
using local headless Google Chrome for inclusion in the visual user guide.

Usage:
    python scripts/generate_docs_screenshots.py [--base-url http://localhost:8000]
"""
import os
import subprocess
import sys
import time

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUTPUT_DIR = os.path.abspath("docs/images/pages")
DEFAULT_BASE_URL = "http://localhost:8000"

# Key Platform Pages for Visual Manual
PAGES = [
    {
        "name": "01_market_overview",
        "url": "/",
        "title": "Market Overview & Executive Dashboard",
    },
    {
        "name": "02_stock_directory",
        "url": "/stocks/",
        "title": "Stock Directory & Search Hub",
    },
    {
        "name": "03_stock_detail_coalindia",
        "url": "/stocks/COALINDIA/",
        "title": "Stock Intelligence Cockpit (Coal India)",
    },
    {
        "name": "04_stock_detail_sbin",
        "url": "/stocks/SBIN/",
        "title": "Stock Intelligence Cockpit (State Bank of India)",
    },
    {
        "name": "05_technical_analysis",
        "url": "/research/technical/",
        "title": "Technical Analysis Desk",
    },
    {
        "name": "06_fundamental_analysis",
        "url": "/research/fundamental/",
        "title": "Fundamental Health & Valuation Engine",
    },
    {
        "name": "07_ai_research_hub",
        "url": "/research/ai/?symbol=SBIN&role=INVESTOR",
        "title": "Multi-Persona AI Stock Research Hub",
    },
    {
        "name": "08_stock_screener",
        "url": "/screener/",
        "title": "Quantitative Stock Screener",
    },
    {
        "name": "09_watchlists_manager",
        "url": "/watchlists/",
        "title": "Watchlists Manager",
    },
    {
        "name": "10_portfolio_holdings",
        "url": "/portfolio/holdings/",
        "title": "Portfolio Holdings & FIFO Tax Lots",
    },
    {
        "name": "11_swing_trading",
        "url": "/trading/",
        "title": "Swing Trading & Position Sizer",
    },
    {
        "name": "12_strategy_backtester",
        "url": "/backtesting/",
        "title": "Strategy Backtesting Simulation Engine",
    },
    {
        "name": "13_ml_risk_dashboard",
        "url": "/ml/risk-dashboard/",
        "title": "Machine Learning Risk Intelligence & Shadow Dashboard",
    },
    {
        "name": "14_ipo_intelligence",
        "url": "/ipo/",
        "title": "IPO Intelligence Centre & Primary Issues Desk",
    },
    {
        "name": "15_papertrading_terminal",
        "url": "/papertrading/",
        "title": "PaperTrading Virtual Brokerage Terminal",
    },
    {
        "name": "16_admin_eod_pipeline",
        "url": "/admin/ml_engine/mlshadowpipelinerun/run-pipeline/",
        "title": "Django Admin: EOD Shadow Pipeline Execution Desk",
    },
]


def capture_screenshot(url: str, output_path: str, width: int = 1440, height: int = 900) -> bool:
    """Captures a screenshot of a URL using Headless Google Chrome."""
    if not os.path.exists(CHROME_BIN):
        print(f"Error: Chrome binary not found at {CHROME_BIN}", file=sys.stderr)
        return False

    cmd = [
        CHROME_BIN,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--window-size={width},{height}",
        f"--screenshot={output_path}",
        url,
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        return res.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"Failed to capture {url}: {e}", file=sys.stderr)
        return False


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"=== KuberLens Documentation Screenshot Generator ===")
    print(f"Target Base URL: {base_url}")
    print(f"Output Directory: {OUTPUT_DIR}\n")

    succeeded = 0
    for page in PAGES:
        full_url = f"{base_url.rstrip('/')}{page['url']}"
        png_path = os.path.join(OUTPUT_DIR, f"{page['name']}.png")
        print(f"Capturing: {page['title']} -> {page['name']}.png ...", end=" ", flush=True)

        ok = capture_screenshot(full_url, png_path)
        if ok:
            size_kb = os.path.getsize(png_path) / 1024
            print(f"DONE ({size_kb:.1f} KB)")
            succeeded += 1
        else:
            print("FAILED (Is the dev server running on port 8000?)")

    print(f"\nCompleted: {succeeded}/{len(PAGES)} screenshots captured successfully.")


if __name__ == "__main__":
    main()
