#!/usr/bin/env python3
"""
KuberLens Playwright Real UI Screenshot Capture & Page Verification Tool.
Captures real high-resolution screenshots directly from the running KuberLens instance
and validates the operational status of every page.
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import get_user_model
from playwright.sync_api import sync_playwright

User = get_user_model()
try:
    user = User.objects.get(username="shreesha")
except User.DoesNotExist:
    user = User.objects.first()

session = SessionStore()
session["_auth_user_id"] = str(user.id)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = user.get_session_auth_hash()
session.save()
session_id = session.session_key

BASE_URL = "http://127.0.0.1:8000"
DOCS_IMG_DIR = os.path.abspath("docs/assets/screenshots")
os.makedirs(DOCS_IMG_DIR, exist_ok=True)

TARGET_PAGES = [
    {"slug": "01_market_dashboard", "url": "/", "title": "Market Dashboard"},
    {"slug": "02_market_overview", "url": "/market-overview/", "title": "Market Overview & Breadth"},
    {"slug": "03_stock_directory", "url": "/stocks/", "title": "Stock Directory"},
    {"slug": "04_stock_intelligence_coalindia", "url": "/stocks/COALINDIA/", "title": "Single Stock Intelligence - COALINDIA"},
    {"slug": "05_stock_intelligence_sbin", "url": "/stocks/SBIN/", "title": "Single Stock Intelligence - SBIN"},
    {"slug": "06_technical_analysis", "url": "/research/technical/", "title": "Technical Analysis Workbench"},
    {"slug": "07_fundamental_analysis", "url": "/research/fundamental/", "title": "Fundamental Health & Valuation Hub"},
    {"slug": "08_ai_stock_research", "url": "/research/ai/?symbol=SBIN&role=INVESTOR", "title": "AI Stock Research Hub"},
    {"slug": "09_ai_recommendations", "url": "/research/ai/recommendations/", "title": "AI Multi-Factor Recommendations"},
    {"slug": "10_stock_screener", "url": "/screener/", "title": "Quantitative Stock Screener"},
    {"slug": "11_sector_analysis", "url": "/stocks/sectors/", "title": "Sector & Industry Heatmap"},
    {"slug": "12_news_events", "url": "/news/", "title": "News & Market Events Feed"},
    {"slug": "13_ipo_dashboard", "url": "/ipo/", "title": "IPO Intelligence Dashboard"},
    {"slug": "14_ipo_primary_issues", "url": "/ipo/issues/", "title": "Primary Issues Desk & GMP"},
    {"slug": "15_ipo_calendar", "url": "/ipo/calendar/", "title": "IPO Interactive Calendar"},
    {"slug": "16_ipo_research", "url": "/ipo/research/", "title": "IPO Financials & RHP Analysis"},
    {"slug": "17_ipo_listing_performance", "url": "/ipo/performance/", "title": "IPO Listing Performance Tracker"},
    {"slug": "18_ipo_compare", "url": "/ipo/compare/", "title": "Compare IPOs Side-by-Side"},
    {"slug": "19_ipo_backtester", "url": "/ipo/backtest/", "title": "IPO Strategy Backtester"},
    {"slug": "20_ipo_family_vault", "url": "/ipo/family-vault/", "title": "Family Demat Vault"},
    {"slug": "21_ipo_applications", "url": "/ipo/applications/", "title": "My IPO Applications"},
    {"slug": "22_portfolio_overview", "url": "/portfolio/", "title": "Portfolio Net Worth & Analytics"},
    {"slug": "23_portfolio_holdings", "url": "/portfolio/holdings/", "title": "Holdings & Position Ledger"},
    {"slug": "24_watchlists", "url": "/watchlists/", "title": "Multi-Watchlist Monitoring"},
    {"slug": "25_investment_journal", "url": "/portfolio/journal/", "title": "Investment Theses Journal"},
    {"slug": "26_paper_trading", "url": "/papertrading/", "title": "Paper Trading Execution Terminal"},
    {"slug": "27_swing_scanner", "url": "/trading/", "title": "Algorithmic Swing Trading Scanner"},
    {"slug": "28_trade_journal", "url": "/trading/journal/", "title": "Trade Execution & Psychological Journal"},
    {"slug": "29_strategy_backtesting", "url": "/backtesting/", "title": "Quantitative Strategy Backtester"},
    {"slug": "30_fo_derivatives", "url": "/brokers/derivatives/", "title": "F&O Derivatives Desk"},
    {"slug": "31_risk_management", "url": "/trading/risk-management/", "title": "Risk & Position Sizing Calculator"},
    {"slug": "32_ml_predictions", "url": "/ml/", "title": "Machine Learning Prediction Engine"},
    {"slug": "33_ml_risk_dashboard", "url": "/ml/risk-dashboard/", "title": "Institutional Risk Veto Dashboard"},
    {"slug": "34_alerts", "url": "/alerts/", "title": "Alerts & Notifications Center"},
    {"slug": "35_data_sources", "url": "/settings/data-sources/", "title": "Market Data Feeds Configuration"},
    {"slug": "36_broker_connections", "url": "/brokers/", "title": "Indian Broker Integrations"},
    {"slug": "37_reports_exports", "url": "/reports/", "title": "Tax P&L & Financial Reports"},
    {"slug": "38_account_profile", "url": "/accounts/profile/", "title": "User Profile & App Settings"},
]

results = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        device_scale_factor=2,  # Crisp retina quality
    )
    # Inject authenticated session
    context.add_cookies([
        {"name": "sessionid", "value": session_id, "domain": "127.0.0.1", "path": "/"}
    ])
    
    page = context.new_page()
    
    for item in TARGET_PAGES:
        target_url = BASE_URL + item["url"]
        screenshot_path = os.path.join(DOCS_IMG_DIR, f"{item['slug']}.png")
        print(f"Testing {item['title']} -> {target_url}")
        
        try:
            response = page.goto(target_url, wait_until="networkidle", timeout=15000)
            status_code = response.status if response else 0
            
            # Allow charts / dynamic widgets to render
            page.wait_for_timeout(1000)
            
            if status_code in (200, 304):
                page.screenshot(path=screenshot_path, full_page=False)
                print(f"  [SUCCESS] Status {status_code} -> Saved {screenshot_path}")
                results.append({
                    "slug": item["slug"],
                    "title": item["title"],
                    "url": item["url"],
                    "status_code": status_code,
                    "status": "VERIFIED WORKING",
                    "screenshot": f"assets/screenshots/{item['slug']}.png",
                    "notes": "Rendered successfully and captured."
                })
            elif status_code in (301, 302):
                page.screenshot(path=screenshot_path, full_page=False)
                results.append({
                    "slug": item["slug"],
                    "title": item["title"],
                    "url": item["url"],
                    "status_code": status_code,
                    "status": "PARTIALLY WORKING",
                    "screenshot": f"assets/screenshots/{item['slug']}.png",
                    "notes": f"Redirected to {page.url}"
                })
            else:
                results.append({
                    "slug": item["slug"],
                    "title": item["title"],
                    "url": item["url"],
                    "status_code": status_code,
                    "status": "INACCESSIBLE",
                    "screenshot": None,
                    "notes": f"HTTP status {status_code}"
                })
        except Exception as e:
            print(f"  [ERROR] {e}")
            results.append({
                "slug": item["slug"],
                "title": item["title"],
                "url": item["url"],
                "status_code": None,
                "status": "INACCESSIBLE",
                "screenshot": None,
                "notes": str(e)
            })

    browser.close()

import json
with open("docs/verification_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nVerification and screenshot capture complete!")
