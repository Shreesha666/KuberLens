import pytest
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.holdings.models import Holding
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.portfolio.models import Portfolio
from apps.trading.models import TradeJournal, TradeJournalStatus

User = get_user_model()


@pytest.fixture
def risk_user_and_portfolio(db):
    user = User.objects.create_user(
        username="risk_trader",
        email="risk_trader@example.com",
        password="testpassword123",
    )
    portfolio = Portfolio.objects.create(
        user=user,
        name="Main Investment Portfolio",
        is_default=True,
    )
    nse, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "National Stock Exchange"})

    inst_rel, _ = Instrument.objects.get_or_create(
        isin="INE002A01018",
        defaults={
            "display_name": "Reliance Industries",
            "legal_name": "Reliance Industries Limited",
            "sector": "Energy",
            "market_cap_category": "LARGE",
        },
    )
    listing_rel, _ = ExchangeListing.objects.get_or_create(
        symbol="RELIANCE",
        exchange=nse,
        defaults={"instrument": inst_rel, "trading_symbol": "RELIANCE-EQ"},
    )

    inst_tcs, _ = Instrument.objects.get_or_create(
        isin="INE467B01029",
        defaults={
            "display_name": "Tata Consultancy Services",
            "legal_name": "Tata Consultancy Services Limited",
            "sector": "Information Technology",
            "market_cap_category": "LARGE",
        },
    )
    listing_tcs, _ = ExchangeListing.objects.get_or_create(
        symbol="TCS",
        exchange=nse,
        defaults={"instrument": inst_tcs, "trading_symbol": "TCS-EQ"},
    )

    # Add a large holding (overallocation test > 20%)
    Holding.objects.create(
        portfolio=portfolio,
        listing=listing_rel,
        total_quantity=100,
        average_buy_price=Decimal("2500.00"),
        invested_amount=Decimal("250000.00"),
        current_price=Decimal("2600.00"),
        current_value=Decimal("260000.00"),
    )

    # Add second holding
    Holding.objects.create(
        portfolio=portfolio,
        listing=listing_tcs,
        total_quantity=20,
        average_buy_price=Decimal("3500.00"),
        invested_amount=Decimal("70000.00"),
        current_price=Decimal("3600.00"),
        current_value=Decimal("72000.00"),
    )

    # Add an open swing trade with stop loss
    TradeJournal.objects.create(
        user=user,
        listing=listing_rel,
        strategy="Oversold Bounce",
        entry_date="2026-11-20",
        entry_price=Decimal("2550.00"),
        quantity=30,
        stop_loss=Decimal("2450.00"),
        target_price=Decimal("2750.00"),
        status=TradeJournalStatus.OPEN,
        checklist_completed=True,
    )

    return user, portfolio


@pytest.mark.django_db
class TestRiskManagementCockpit:
    def test_risk_management_view_redirects_unauthenticated(self):
        client = Client()
        url = reverse("trading:risk_management")
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_risk_management_view_full_page(self, risk_user_and_portfolio):
        user, _ = risk_user_and_portfolio
        client = Client()
        client.force_login(user)

        url = reverse("trading:risk_management")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Risk Management Cockpit" in content
        assert "Total Open Stop Risk" in content
        assert "Quantitative Position Sizer" in content
        assert "Portfolio Concentration" in content
        assert "Active Swing Trades" in content
        assert "RELIANCE" in content

    def test_risk_management_htmx_partial_swap(self, risk_user_and_portfolio):
        user, _ = risk_user_and_portfolio
        client = Client()
        client.force_login(user)

        url = reverse("trading:risk_management")
        response = client.get(url, HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        content = response.content.decode()

        assert "<!DOCTYPE html>" not in content
        assert "Risk Management Cockpit" in content
        assert "position-sizer-form" in content

    def test_risk_management_module_alias_url(self, risk_user_and_portfolio):
        """Verifies that accessing /modules/risk_management/ directly loads the cockpit."""
        user, _ = risk_user_and_portfolio
        client = Client()
        client.force_login(user)

        url = reverse("dashboard:risk_management_alias")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()
        assert "Risk Management Cockpit" in content
        assert "Module Shell" not in content  # Placeholder is replaced

    def test_position_sizer_calculation_endpoint(self, risk_user_and_portfolio):
        user, _ = risk_user_and_portfolio
        client = Client()
        client.force_login(user)

        url = reverse("trading:calculate_size") + "?capital=500000&risk_pct=1.5&entry=1000&stop_loss=950&target=1150"
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode()

        assert "Risk Sizing Summary" in content
        # Risk amount = 500,000 * 1.5% = 7,500. Risk per share = 50. Qty = 150.
        assert "150" in content
        assert "1 : 3.0" in content
