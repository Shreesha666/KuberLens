"""
UI and Navigation tests for AI Research Hub and Tab views.
"""
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.ai_analysis.models import AIRole
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote


@pytest.mark.django_db
class TestAIViews:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="aiviewuser",
            email="aiviewuser@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE009A01021",
            display_name="INFY",
            legal_name="Infosys Limited",
            sector="Technology",
            industry="IT Services",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="INFY",
            trading_symbol="INFY-EQ",
            is_primary=True,
            is_tradeable=True,
        )
        MarketQuote.objects.create(
            listing=self.listing,
            price=Decimal("1850.00"),
            change=Decimal("15.00"),
            change_percent=Decimal("0.82"),
            open=Decimal("1840.00"),
            high=Decimal("1860.00"),
            low=Decimal("1835.00"),
            close=Decimal("1850.00"),
            previous_close=Decimal("1835.00"),
            volume=800000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
            freshness_status="FRESH",
            source_type="DIRECT",
        )

    def test_ai_hub_view_full_page_and_htmx(self):
        url = reverse("ai_analysis:hub")

        # Full page load
        res = self.client.get(url, {"symbol": "INFY", "role": "INVESTOR"})
        assert res.status_code == 200
        content = res.content.decode()
        assert "AI Stock Research Engine" in content
        assert "INFY" in content
        assert "Investor AI" in content

        # HTMX partial load
        htmx_res = self.client.get(url, {"symbol": "INFY", "role": "SWING_TRADER"}, HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        htmx_content = htmx_res.content.decode()
        assert "Swing Trader AI" in htmx_content
        assert "<!DOCTYPE html>" not in htmx_content

    def test_ai_stock_detail_tab_partial_endpoint(self):
        url = reverse("ai_analysis:stock_tab_partial", kwargs={"symbol": "INFY"})
        res = self.client.get(url, {"role": AIRole.INVESTOR})

        assert res.status_code == 200
        content = res.content.decode()
        assert "INFY" in content
        assert "Executive Research Synthesis" in content
        assert "Positive Factors &amp; Catalysts" in content or "Positive Factors & Catalysts" in content

    def test_unauthenticated_user_redirect(self):
        self.client.logout()
        url = reverse("ai_analysis:hub")
        res = self.client.get(url)
        assert res.status_code == 302
        assert "/accounts/login/" in res.url

    def test_ai_recommendations_full_shell_and_htmx(self):
        url = reverse("ai_analysis:recommendations")

        # Full page load
        res = self.client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "<!DOCTYPE html>" in content
        assert "AI Investment Recommendations" in content
        assert "Guidance for Existing Holdings" in content
        assert "Opportunities for Prospective Investors" in content

        # HTMX partial load
        htmx_res = self.client.get(url, HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        htmx_content = htmx_res.content.decode()
        assert "<!DOCTYPE html>" not in htmx_content
        assert "AI Investment Recommendations" in htmx_content

    def test_ai_recommendations_alias_url(self):
        url = "/modules/ai_recommendations/"
        res = self.client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "AI Investment Recommendations" in content
        assert "AI Recommendations Module Shell" not in content

    def test_ai_recommendations_filtering(self):
        url = reverse("ai_analysis:recommendations")

        # Filter by tab
        res_tab = self.client.get(url, {"tab": "opportunities"})
        assert res_tab.status_code == 200
        content_tab = res_tab.content.decode()
        assert "Opportunities for Prospective Investors" in content_tab

        # Filter by search query
        res_query = self.client.get(url, {"q": "INFY"})
        assert res_query.status_code == 200
        content_query = res_query.content.decode()
        assert "INFY" in content_query
