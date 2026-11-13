"""
Tests for Portfolio and Holdings Views.
Verifies full-page rendering, HTMX partial rendering, transaction logging, and authentication protection.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.holdings.models import HoldingTransaction, TransactionType
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.portfolio.models import Portfolio
from services.portfolio.accounting import FIFOAccountingEngine

User = get_user_model()


@pytest.fixture
def view_setup(db, client):
    user = User.objects.create_user(
        username="trader_views",
        email="trader@example.com",
        password="password123",
    )
    portfolio = Portfolio.objects.create(
        user=user,
        name="Wealth Builder",
        currency="INR",
        cash_balance=Decimal("200000.00"),
    )
    exchange = Exchange.objects.create(code="NSE", name="NSE")
    instrument = Instrument.objects.create(
        isin="INE009A01021",
        display_name="Infosys",
        legal_name="Infosys Limited",
        sector="Technology",
        industry="IT Services",
    )
    listing = ExchangeListing.objects.create(
        instrument=instrument,
        exchange=exchange,
        symbol="INFY",
        is_tradeable=True,
    )

    # Buy 50 shares @ 1500
    HoldingTransaction.objects.create(
        portfolio=portfolio,
        listing=listing,
        transaction_type=TransactionType.BUY,
        quantity=50,
        price=Decimal("1500.00"),
        brokerage=Decimal("20.00"),
        statutory_taxes=Decimal("15.00"),
        executed_at=timezone.now() - timedelta(days=10),
    )
    FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("1600.00"))

    client.force_login(user)
    return {
        "user": user,
        "portfolio": portfolio,
        "listing": listing,
        "client": client,
    }


@pytest.mark.django_db
class TestPortfolioViews:
    def test_portfolio_overview_full_page(self, view_setup):
        client = view_setup["client"]
        url = reverse("portfolio:overview")
        resp = client.get(url)

        assert resp.status_code == 200
        assert "portfolio/overview.html" in [t.name for t in resp.templates]
        assert "Total Net Worth" in resp.content.decode()
        assert "INFY" in resp.content.decode()

    def test_portfolio_overview_htmx_partial(self, view_setup):
        client = view_setup["client"]
        url = reverse("portfolio:overview")
        resp = client.get(url, HTTP_HX_REQUEST="true")

        assert resp.status_code == 200
        assert "portfolio/partials/overview_partial.html" in [t.name for t in resp.templates]
        assert "<!DOCTYPE html>" not in resp.content.decode()
        assert "Total Net Worth" in resp.content.decode()

    def test_holding_list_full_and_htmx(self, view_setup):
        client = view_setup["client"]
        url = reverse("holdings:list")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "holdings/holding_list.html" in [t.name for t in resp_full.templates]
        assert "INFY" in resp_full.content.decode()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "holdings/partials/holding_list_partial.html" in [t.name for t in resp_htmx.templates]
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_holding_detail_view(self, view_setup):
        client = view_setup["client"]
        listing = view_setup["listing"]
        url = reverse("holdings:detail", kwargs={"symbol": listing.symbol})

        # Full page
        resp = client.get(url)
        assert resp.status_code == 200
        assert "holdings/holding_detail.html" in [t.name for t in resp.templates]
        assert "Active FIFO Lots" in resp.content.decode()
        assert "Existing Holder Strategy" in resp.content.decode()
        assert "New Prospective Investor" in resp.content.decode()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "holdings/partials/holding_detail_partial.html" in [t.name for t in resp_htmx.templates]
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_add_transaction_view_get_full_and_htmx(self, view_setup):
        client = view_setup["client"]
        url = reverse("holdings:add_transaction")

        # Full page direct load
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "holdings/add_transaction.html" in [t.name for t in resp_full.templates]
        content_full = resp_full.content.decode()
        assert "Add Investment &amp; Record Transaction" in content_full or "Add Investment & Record Transaction" in content_full
        assert "Estimated Total Capital Outlay" in content_full

        # HTMX partial load
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "holdings/partials/add_transaction_partial.html" in [t.name for t in resp_htmx.templates]
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_add_transaction_view_get_with_prefilled_symbol(self, view_setup):
        client = view_setup["client"]
        listing = view_setup["listing"]
        url = f"{reverse('holdings:add_transaction')}?symbol={listing.symbol}"

        resp = client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert listing.symbol in content
        assert "stock-info-banner" in content

    def test_add_investment_and_buy_stock_navigation_links(self, view_setup):
        client = view_setup["client"]
        listing = view_setup["listing"]

        # 1. Portfolio Overview has "Add Investment" link
        resp_overview = client.get(reverse("portfolio:overview"))
        assert resp_overview.status_code == 200
        assert reverse("holdings:add_transaction") in resp_overview.content.decode()

        # 2. Holdings list has "Buy New Stock" link
        resp_holdings = client.get(reverse("holdings:list"))
        assert resp_holdings.status_code == 200
        assert reverse("holdings:add_transaction") in resp_holdings.content.decode()

        # 3. Stock detail has "Add to Portfolio" link with pre-filled symbol
        resp_stock = client.get(reverse("stocks:stock_detail", kwargs={"symbol": listing.symbol}))
        assert resp_stock.status_code == 200
        assert f"{reverse('holdings:add_transaction')}?symbol={listing.symbol}" in resp_stock.content.decode()

    def test_add_transaction_post_and_htmx_redirect(self, view_setup):
        client = view_setup["client"]
        listing = view_setup["listing"]
        portfolio = view_setup["portfolio"]
        url = reverse("holdings:add_transaction")

        post_data = {
            "symbol": listing.symbol,
            "transaction_type": "BUY",
            "quantity": 25,
            "price": "1550.00",
            "brokerage": "20.00",
            "statutory_taxes": "10.00",
            "notes": "Added on pullback",
        }

        # Regular POST
        resp = client.post(url, data=post_data)
        assert resp.status_code == 302
        assert reverse("holdings:detail", kwargs={"symbol": listing.symbol}) in resp["Location"]

        # Re-check holding state
        holding = FIFOAccountingEngine.reconcile_holding(portfolio, listing, current_price=Decimal("1600.00"))
        assert holding.total_quantity == 75  # 50 + 25

        # HTMX POST
        post_data["quantity"] = 15
        resp_htmx = client.post(url, data=post_data, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 302
        assert resp_htmx.has_header("HX-Redirect")

    def test_anonymous_user_redirected_to_login(self, client):
        client.logout()
        resp = client.get(reverse("portfolio:overview"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp["Location"]

    def test_portfolio_import_view_get_full_and_htmx(self, view_setup):
        client = view_setup["client"]
        url = reverse("portfolio:import_holdings")

        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "portfolio/import_holdings.html" in [t.name for t in resp_full.templates]
        assert "Import Holdings from Broker / CSV" in resp_full.content.decode()

        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "portfolio/partials/import_holdings_partial.html" in [t.name for t in resp_htmx.templates]

    def test_portfolio_import_view_post_pasted_csv(self, view_setup):
        client = view_setup["client"]
        portfolio = view_setup["portfolio"]
        url = reverse("portfolio:import_holdings")

        raw_csv = (
            '"Instrument","Qty.","Avg. cost","LTP"\n'
            '"TCS",50,3500.00,3800.00\n'
            '"HDFCBANK",100,1600.00,1750.00\n'
        )

        resp = client.post(url, data={"csv_text": raw_csv, "clear_existing": "on"})
        assert resp.status_code == 302
        assert resp["Location"] == reverse("portfolio:overview")

        from apps.holdings.models import Holding
        holdings = list(Holding.objects.filter(portfolio=portfolio, total_quantity__gt=0).order_by("listing__symbol"))
        assert len(holdings) == 2
        symbols = [h.listing.symbol for h in holdings]
        assert "HDFCBANK" in symbols
        assert "TCS" in symbols

    def test_portfolio_import_view_post_file(self, view_setup):
        from django.core.files.uploadedfile import SimpleUploadedFile
        client = view_setup["client"]
        url = reverse("portfolio:import_holdings")

        file_content = b'"Symbol","Quantity","Avg Price","LTP"\n"WIPRO",200,450.00,520.00\n'
        uploaded_file = SimpleUploadedFile("holdings.csv", file_content, content_type="text/csv")

        resp = client.post(url, data={"csv_file": uploaded_file})
        assert resp.status_code == 302
        assert resp["Location"] == reverse("portfolio:overview")

    def test_portfolio_import_view_empty_data_shows_error(self, view_setup):
        client = view_setup["client"]
        url = reverse("portfolio:import_holdings")

        resp = client.post(url, data={"csv_text": ""})
        assert resp.status_code == 200
        assert "Please provide CSV data" in resp.content.decode()

    def test_investment_journal_list_view_and_htmx(self, view_setup):
        client = view_setup["client"]
        url = reverse("portfolio:investment_journal")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        content = resp_full.content.decode()
        assert "Investment Journal" in content

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_investment_journal_create_and_delete_flow(self, view_setup):
        client = view_setup["client"]
        add_url = reverse("portfolio:investment_journal_add")

        post_data = {
            "symbol": "INFY",
            "title": "Digital Transformation Compounder",
            "thesis_narrative": "Infosys has structural cost advantages and expanding enterprise cloud deals.",
            "moat_description": "Global scale, sticky client relationships",
            "conviction": "HIGH",
            "horizon": "3_YEARS",
            "target_price": "2200.00",
            "catalysts": "Large deal ramp ups in Q3",
            "key_risks": "Global enterprise slowdown",
        }

        resp = client.post(add_url, data=post_data)
        assert resp.status_code == 302

        from apps.portfolio.models import InvestmentJournalEntry
        entry = InvestmentJournalEntry.objects.filter(listing__symbol="INFY").first()
        assert entry is not None
        assert entry.title == "Digital Transformation Compounder"
        assert entry.target_price == Decimal("2200.00")

        # Delete entry
        del_url = reverse("portfolio:investment_journal_delete", kwargs={"pk": entry.pk})
        resp_del = client.post(del_url)
        assert resp_del.status_code == 302
        assert not InvestmentJournalEntry.objects.filter(pk=entry.pk).exists()
