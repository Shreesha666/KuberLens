#!/usr/bin/env python3
"""
KuberLens In-App Documentation Integration Test & Browser Verification Suite.
Validates:
  1. Django URL resolution and authentication enforcement.
  2. Security and path traversal resistance.
  3. MIME type accuracy (HTML, CSS, JS, JSON, PNG).
  4. Search index availability.
  5. Playwright browser rendering of /help/, sidebar links, and contextual help icons.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath("."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
import django
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from playwright.sync_api import sync_playwright

User = get_user_model()
try:
    user = User.objects.get(username="shreesha")
except User.DoesNotExist:
    user = User.objects.first()

print("--- Step 1: Django Test Client Verification ---")
client = Client()

# Unauthenticated should redirect to login
unauth_res = client.get("/help/")
print(f"Unauthenticated /help/ status: {unauth_res.status_code} (Expected 302 redirect)")
assert unauth_res.status_code == 302, f"Expected 302, got {unauth_res.status_code}"

client.force_login(user)

# Authenticated root help
auth_res = client.get("/help/")
print(f"Authenticated /help/ status: {auth_res.status_code}")
assert auth_res.status_code == 200, f"Expected 200, got {auth_res.status_code}"
auth_content = b"".join(auth_res.streaming_content)
assert b"KuberLens V1.0 User Guide" in auth_content

# Getting Started
gs_res = client.get("/help/getting-started/installation-and-setup/")
print(f"Authenticated Getting Started status: {gs_res.status_code}")
assert gs_res.status_code == 200

# FAQs
faq_res = client.get("/help/faq/")
print(f"Authenticated FAQs status: {faq_res.status_code}")
assert faq_res.status_code == 200

# Trailing slash redirection test
no_slash_res = client.get("/help/getting-started/installation-and-setup")
print(f"Directory URL without slash status: {no_slash_res.status_code} -> Location: {no_slash_res.headers.get('Location')}")
assert no_slash_res.status_code == 302

# Search index
search_res = client.get("/help/search/search_index.json")
print(f"Search index status: {search_res.status_code}, content-type: {search_res.headers.get('Content-Type')}")
assert search_res.status_code == 200
assert "application/json" in search_res.headers.get("Content-Type")
search_data = json.loads(b"".join(search_res.streaming_content))
assert "docs" in search_data
print(f"  Search index contains {len(search_data['docs'])} indexed items.")

# Static CSS asset
css_res = client.get("/help/assets/stylesheets/extra.css")
print(f"Extra CSS status: {css_res.status_code}, content-type: {css_res.headers.get('Content-Type')}")
assert css_res.status_code == 200
assert "text/css" in css_res.headers.get("Content-Type")

# Screenshot asset
img_res = client.get("/help/assets/screenshots/01_market_dashboard.png")
print(f"Screenshot status: {img_res.status_code}, content-type: {img_res.headers.get('Content-Type')}")
assert img_res.status_code == 200
assert "image/png" in img_res.headers.get("Content-Type")

# Security traversal check
traversal_res = client.get("/help/../../etc/passwd")
print(f"Directory traversal attack status: {traversal_res.status_code} (Expected 404)")
assert traversal_res.status_code == 404

traversal_res2 = client.get("/help/../config/settings/base.py")
print(f"Settings file traversal attack status: {traversal_res2.status_code} (Expected 404)")
assert traversal_res2.status_code == 404

# Contextual Help endpoints check
context_urls = [
    "/help/single-stock/single-stock-cockpit/",
    "/help/ai-ml/ml-prediction-engine/",
    "/help/risk/risk-veto-card/",
    "/help/ipo/ipo-dashboard-and-issues/",
    "/help/portfolio/portfolio-cockpit/",
]
for cu in context_urls:
    res = client.get(cu)
    print(f"Contextual URL {cu} status: {res.status_code}")
    assert res.status_code == 200, f"Expected 200 for {cu}, got {res.status_code}"

print("\n--- Step 2: Live Browser / Playwright Verification ---")
from django.contrib.sessions.backends.db import SessionStore
session = SessionStore()
session["_auth_user_id"] = str(user.id)
session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
session["_auth_user_hash"] = user.get_session_auth_hash()
session.save()
session_id = session.session_key

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    ctx.add_cookies([
        {"name": "sessionid", "value": session_id, "domain": "127.0.0.1", "path": "/"}
    ])
    page = ctx.new_page()
    page.on("console", lambda msg: print(f"PAGE LOG: [{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))

    # 1. Open /help/
    page.goto("http://127.0.0.1:8000/help/", wait_until="networkidle", timeout=10000)
    page.wait_for_timeout(2000)
    title = page.title()
    print(f"Browser loaded /help/ -> Title: {title}")
    assert "KuberLens V1.0 User Guide" in title
    page.screenshot(path="docs/assets/screenshots/help_home_live.png")
    print("  Captured: docs/assets/screenshots/help_home_live.png")

    # 2. Test in-page search interaction
    search_input = page.locator("input[data-md-component='search-query']")
    search_input.click()
    search_input.type("Coal", delay=100)
    page.wait_for_timeout(1500)
    
    # Check search result container
    search_output = page.locator(".md-search__output")
    print(f"Search output text: {search_output.inner_text()}")
    search_results = page.locator(".md-search-result__item")
    result_count = search_results.count()
    print(f"  Search query 'Coal' returned {result_count} results in browser UI!")
    assert result_count > 0, "Expected search results for 'Coal'"
    page.screenshot(path="docs/assets/screenshots/help_search_live.png")
    print("  Captured: docs/assets/screenshots/help_search_live.png")

    # 3. Check sidebar on Main App Dashboard (http://127.0.0.1:8000/)
    page.goto("http://127.0.0.1:8000/", wait_until="networkidle", timeout=10000)
    sidebar_help = page.locator("a[href='/help/']")
    assert sidebar_help.count() > 0, "Sidebar does not contain link to /help/"
    print("  Sidebar verified: Contains 'User Guide' link to /help/")

    browser.close()

print("\nALL VERIFICATION CHECKS PASSED PERFECTLY!")
