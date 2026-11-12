"""
Unit and Integration Tests for Machine Learning Engine (Phase 9).
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CustomUser
from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import HistoricalCandle, MarketQuote
from apps.ml_engine.models import MarketRegimeType, MLModelRecord, MLPredictionLabel
from services.ml.engine import MarketRegimeClassifier, StockMLRanker


@pytest.mark.django_db
class TestMLEngine:
    @pytest.fixture(autouse=True)
    def setup_data(self, client):
        self.client = client
        self.user = CustomUser.objects.create_user(
            username="mluser",
            email="mluser@example.com",
            password="testpassword123",
        )
        self.client.force_login(self.user)

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
        self.quote = MarketQuote.objects.create(
            listing=self.listing,
            price=Decimal("4100.00"),
            change=Decimal("35.00"),
            change_percent=Decimal("0.86"),
            open=Decimal("4080.00"),
            high=Decimal("4120.00"),
            low=Decimal("4070.00"),
            close=Decimal("4100.00"),
            previous_close=Decimal("4065.00"),
            volume=800000,
            source_timestamp=timezone.now(),
            retrieved_at=timezone.now(),
        )

        now = timezone.now()
        base_price = 3800.0
        for i in range(60, 0, -1):
            c_timestamp = now - timedelta(days=i)
            p = base_price + (60 - i) * 5.0
            HistoricalCandle.objects.create(
                listing=self.listing,
                timestamp=c_timestamp,
                interval="1d",
                open=Decimal(str(round(p - 3, 2))),
                high=Decimal(str(round(p + 8, 2))),
                low=Decimal(str(round(p - 4, 2))),
                close=Decimal(str(round(p, 2))),
                volume=500000,
                source_provider="TEST",
            )

    def test_market_regime_classifier(self):
        candles = list(HistoricalCandle.objects.filter(listing=self.listing).order_by("timestamp"))
        regime_info = MarketRegimeClassifier.classify_regime(candles)
        assert regime_info["regime"] in MarketRegimeType.values

    def test_stock_ml_ranker_prediction(self):
        pred = StockMLRanker.evaluate_and_predict(self.listing)
        assert pred is not None
        assert pred.listing == self.listing
        assert pred.prediction_label in MLPredictionLabel.values
        assert Decimal("0.0000") <= pred.confidence_score <= Decimal("1.0000")
        assert pred.regime_classification in MarketRegimeType.values
        assert isinstance(pred.feature_contributions, dict)
        assert "Predictive research opinion" in pred.disclaimer

        # Check model record
        model_rec = MLModelRecord.objects.first()
        assert model_rec is not None
        assert model_rec.is_active is True
        assert "accuracy" in model_rec.evaluation_metrics
        assert "naive_momentum_accuracy" in model_rec.baseline_metrics

    def test_ml_dashboard_view_get(self):
        url = reverse("ml_engine:dashboard")
        resp = self.client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Machine Learning &amp; Market Regime Engine" in content or "Machine Learning & Market Regime Engine" in content
        assert "Mandatory Regulatory Research Notice" in content

    def test_ml_dashboard_view_htmx(self):
        url = reverse("ml_engine:dashboard")
        resp = self.client.get(url, HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        assert "Trending Expansion" in resp.content.decode()

    def test_ml_dashboard_filters(self):
        StockMLRanker.evaluate_and_predict(self.listing)
        url = reverse("ml_engine:dashboard")
        resp = self.client.get(f"{url}?label=BULLISH_EXPANSION")
        assert resp.status_code == 200

    def test_ml_regenerate_post(self):
        url = reverse("ml_engine:regenerate")
        resp = self.client.post(url)
        assert resp.status_code == 302
        assert resp.url == reverse("ml_engine:dashboard")
