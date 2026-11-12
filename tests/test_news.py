"""
Tests for News and Corporate Events models and views.
"""
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.news.models import (
    CorporateEvent,
    CorporateEventType,
    EventStatus,
    NewsArticle,
    NewsCategory,
    SentimentType,
)


@pytest.mark.django_db
class TestNewsAndCorporateEvents:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="newsreader",
            email="newsreader@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

        self.exchange = Exchange.objects.create(code="NSE", name="National Stock Exchange", country="India", currency="INR")
        self.inst = Instrument.objects.create(
            isin="INE002A01018",
            display_name="RELIANCE",
            legal_name="Reliance Industries Limited",
            sector="Energy",
            industry="Refineries",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="RELIANCE",
            trading_symbol="RELIANCE-EQ",
            is_primary=True,
            is_tradeable=True,
        )

    def test_news_article_creation_and_feed_view(self):
        NewsArticle.objects.create(
            listing=self.listing,
            headline="Reliance Q2 Profit Exceeds Street Consensus",
            source="NSE Filings",
            published_at=timezone.now(),
            summary="Strong retail and telecom revenue growth propelled quarterly EBITDA.",
            category=NewsCategory.QUARTERLY_RESULTS,
            sentiment=SentimentType.BULLISH,
            is_ai_summary=False,
        )

        url = reverse("news:feed")

        # Full page load
        res = self.client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "News &amp; Corporate Events" in content or "News & Corporate Events" in content
        assert "Reliance Q2 Profit Exceeds Street Consensus" in content
        assert "RELIANCE" in content

        # HTMX partial load with category filter
        htmx_res = self.client.get(url, {"category": "QUARTERLY_RESULTS"}, HTTP_HX_REQUEST="true")
        assert htmx_res.status_code == 200
        htmx_content = htmx_res.content.decode()
        assert "Reliance Q2 Profit" in htmx_content
        assert "<!DOCTYPE html>" not in htmx_content

    def test_news_search_filter(self):
        NewsArticle.objects.create(
            listing=self.listing,
            headline="Special Dividend Declared by Reliance",
            source="BSE Announcements",
            published_at=timezone.now(),
            summary="Interim payout approved by board.",
            category=NewsCategory.DIVIDEND,
            sentiment=SentimentType.BULLISH,
        )

        url = reverse("news:feed")
        res = self.client.get(url, {"q": "Dividend"})
        assert res.status_code == 200
        assert "Special Dividend Declared" in res.content.decode()

    def test_corporate_events_calendar_view(self):
        CorporateEvent.objects.create(
            listing=self.listing,
            event_type=CorporateEventType.DIVIDEND,
            event_date=timezone.now().date() + timedelta(days=5),
            title="RELIANCE - Interim Dividend Ex-Date",
            details="Dividend of ₹10.00 per equity share.",
            ratio_or_value="₹10.00 / share",
            status=EventStatus.UPCOMING,
        )

        url = reverse("news:calendar")
        res = self.client.get(url)
        assert res.status_code == 200
        content = res.content.decode()
        assert "Corporate Actions &amp; Events Calendar" in content or "Corporate Actions & Events Calendar" in content
        assert "RELIANCE" in content
        assert "₹10.00 / share" in content
