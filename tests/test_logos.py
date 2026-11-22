"""
Unit tests for Company Logo Proxy, Service, and Template Tag.
"""
import pytest
from django.core.cache import cache
from django.template import Context, Template
from django.test import Client
from django.urls import reverse

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from services.logos import CompanyLogoService


@pytest.mark.django_db
class TestCompanyLogos:
    @pytest.fixture(autouse=True)
    def setup_data(self):
        cache.clear()
        self.client = Client()
        self.exchange = Exchange.objects.create(
            code="NSE", name="National Stock Exchange", country="India", currency="INR"
        )
        self.inst = Instrument.objects.create(
            isin="INE467B01029",
            display_name="TCS",
            legal_name="Tata Consultancy Services Limited",
            sector="Technology",
            industry="IT Services",
            market_cap_category="LARGE",
        )
        self.listing = ExchangeListing.objects.create(
            instrument=self.inst,
            exchange=self.exchange,
            symbol="TCS",
            trading_symbol="TCS-EQ",
            is_primary=True,
            is_tradeable=True,
        )

    def test_fallback_monogram_generation(self):
        svg_bytes = CompanyLogoService.generate_fallback_monogram("TCS")
        svg_text = svg_bytes.decode("utf-8")
        assert "<svg" in svg_text
        assert "TCS" in svg_text
        assert "</svg>" in svg_text

    def test_stock_logo_proxy_view_returns_svg(self):
        url = reverse("stocks:stock_logo", kwargs={"symbol": "TCS"})
        response = self.client.get(url)

        assert response.status_code == 200
        assert "image/svg+xml" in response["Content-Type"]
        assert "Cache-Control" in response
        assert "max-age" in response["Cache-Control"]
        assert len(response.content) > 0
        assert "<svg" in response.content.decode("utf-8", errors="ignore")

    def test_stock_logo_caching_behavior(self):
        url = reverse("stocks:stock_logo", kwargs={"symbol": "INFY"})
        cache_key = f"{CompanyLogoService.CACHE_KEY_PREFIX}INFY"
        cache.delete(cache_key)

        assert cache.get(cache_key) is None
        response = self.client.get(url)
        assert response.status_code == 200
        assert cache.get(cache_key) is not None

        # Subsequent call uses cache
        cached_response = self.client.get(url)
        assert cached_response.status_code == 200
        assert cached_response.content == response.content

    def test_stock_logo_template_tag(self):
        # 1. String symbol
        tpl = Template("{% load core_tags %}{% stock_logo 'RELIANCE' size=48 %}")
        rendered = tpl.render(Context({}))
        assert '<img src="/stocks/RELIANCE/logo/"' in rendered
        assert 'width="48"' in rendered
        assert 'height="48"' in rendered
        assert 'class="stock-logo rounded flex-shrink-0 border"' in rendered

        # 2. Listing object
        tpl2 = Template("{% load core_tags %}{% stock_logo listing size=32 %}")
        rendered2 = tpl2.render(Context({"listing": self.listing}))
        assert '<img src="/stocks/TCS/logo/"' in rendered2
        assert 'width="32"' in rendered2

    def test_stock_detail_and_holdings_include_stock_logo(self):
        # Stock detail
        detail_url = reverse("stocks:stock_detail", kwargs={"symbol": "TCS"})
        res = self.client.get(detail_url)
        assert res.status_code == 200
        assert '/stocks/TCS/logo/' in res.content.decode("utf-8")

