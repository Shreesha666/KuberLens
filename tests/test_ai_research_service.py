"""
Integration tests for AIResearchService and persistence.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.ai_analysis.models import AIRole, StockAIAnalysis
from apps.fundamental_analysis.models import FundamentalSnapshot
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from services.ai.researcher import AIResearchService


@pytest.mark.django_db
class TestAIResearchService:
    @pytest.fixture(autouse=True)
    def setup_entities(self):
        self.user = CustomUser.objects.create_user(
            username="airesearcher",
            email="airesearcher@example.com",
            password="testpassword123",
        )
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

    def test_gather_structured_context_detects_missing_info(self):
        # Listing without quote or snapshots
        context = AIResearchService.gather_structured_context(self.listing, user=self.user)

        assert context["symbol"] == "RELIANCE"
        assert context["company_name"] == "Reliance Industries Limited"
        assert len(context["missing_information"]) > 0
        assert any("quote unavailable" in m for m in context["missing_information"])
        assert any("Technical indicator snapshot missing" in m for m in context["missing_information"])
        assert any("Fundamental financial statement snapshot" in m for m in context["missing_information"])

    def test_analyze_stock_persists_analysis(self):
        # Create quote and snapshot
        MarketQuote.objects.create(
            listing=self.listing,
            price=Decimal("2900.00"),
            change=Decimal("35.00"),
            change_percent=Decimal("1.22"),
            open=Decimal("2880.00"),
            high=Decimal("2920.00"),
            low=Decimal("2870.00"),
            close=Decimal("2900.00"),
            previous_close=Decimal("2865.00"),
            volume=1500000,
            source_provider="JUGAAD",
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
            freshness_status="FRESH",
            source_type="DIRECT",
        )
        TechnicalIndicatorSnapshot.objects.create(
            listing=self.listing,
            interval="1D",
            timestamp=timezone.now(),
            trend_signal="BULLISH",
            sma_20=Decimal("2850.00"),
            sma_50=Decimal("2800.00"),
            sma_200=Decimal("2600.00"),
            rsi_14=Decimal("58.5"),
            atr_14=Decimal("38.00"),
        )
        FundamentalSnapshot.objects.create(
            instrument=self.inst,
            overall_score=78,
            pe_ratio=Decimal("24.5"),
            sector_pe=Decimal("26.0"),
            roe=Decimal("14.8"),
            debt_to_equity=Decimal("0.45"),
        )

        analysis = AIResearchService.analyze_stock(
            listing=self.listing,
            role=AIRole.INVESTOR,
            user=self.user,
            force_refresh=True,
        )

        assert isinstance(analysis, StockAIAnalysis)
        assert analysis.listing == self.listing
        assert analysis.role == AIRole.INVESTOR
        assert analysis.overall_view in ["BUY_CANDIDATE", "HOLD"]
        assert len(analysis.positive_factors) > 0
        assert "Reliance" in analysis.summary
        assert analysis.technical_analysis.get("sma_200") == 2600.0

        # Verify caching (calling again without force_refresh returns same instance)
        cached_analysis = AIResearchService.analyze_stock(
            listing=self.listing,
            role=AIRole.INVESTOR,
            user=self.user,
            force_refresh=False,
        )
        assert cached_analysis.pk == analysis.pk
