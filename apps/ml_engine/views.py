"""
Machine Learning and Market Regime Analytics Views.
"""
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from apps.ml_engine.models import MarketRegimeType, MLPrediction, MLPredictionLabel
from services.ml.engine import StockMLRanker

POPULAR_ML_SYMBOLS = [
    "RELIANCE",
    "TCS",
    "HDFCBANK",
    "INFY",
    "TATAMOTORS",
    "ICICIBANK",
    "LT",
    "ITC",
    "BHARTIARTL",
    "KOTAKBANK",
]


class MLPredictionsDashboardView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    ML Regime & Predictive Analytics Dashboard.
    """
    template_name = "ml_engine/dashboard.html"
    partial_template_name = "ml_engine/partials/dashboard_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        label_filter = self.request.GET.get("label", "").strip()
        regime_filter = self.request.GET.get("regime", "").strip()

        # If no predictions exist, initialize predictions for top liquid symbols
        if not MLPrediction.objects.exists():
            for sym in POPULAR_ML_SYMBOLS:
                listing = ExchangeListing.objects.filter(symbol=sym, is_tradeable=True).first()
                if listing:
                    StockMLRanker.evaluate_and_predict(listing)

        qs = MLPrediction.objects.select_related("listing__instrument", "model_record").all()

        if label_filter and label_filter in MLPredictionLabel.values:
            qs = qs.filter(prediction_label=label_filter)

        if regime_filter and regime_filter in MarketRegimeType.values:
            qs = qs.filter(regime_classification=regime_filter)

        predictions = qs.order_by("-confidence_score")[:30]

        # Aggregate Regime Distribution Stats
        total_preds = MLPrediction.objects.count()
        trending_up_count = MLPrediction.objects.filter(regime_classification=MarketRegimeType.TRENDING_UP).count()
        range_bound_count = MLPrediction.objects.filter(regime_classification=MarketRegimeType.RANGE_BOUND).count()
        high_vol_count = MLPrediction.objects.filter(regime_classification=MarketRegimeType.HIGH_VOLATILITY).count()

        trending_pct = round((trending_up_count / total_preds * 100), 1) if total_preds > 0 else 0
        range_pct = round((range_bound_count / total_preds * 100), 1) if total_preds > 0 else 0
        vol_pct = round((high_vol_count / total_preds * 100), 1) if total_preds > 0 else 0

        context["active_nav"] = "ml_predictions"
        context["predictions"] = predictions
        context["selected_label"] = label_filter
        context["selected_regime"] = regime_filter
        context["prediction_labels"] = MLPredictionLabel.choices
        context["regime_types"] = MarketRegimeType.choices
        context["trending_pct"] = trending_pct
        context["range_pct"] = range_pct
        context["vol_pct"] = vol_pct
        context["total_predictions"] = total_preds
        return context


class MLRegeneratePredictionsView(LoginRequiredMixin, View):
    """
    Refreshes ML predictions across frontline universe stocks.
    """
    def post(self, request, *args, **kwargs):
        count = 0
        for sym in POPULAR_ML_SYMBOLS:
            listing = ExchangeListing.objects.filter(symbol=sym, is_tradeable=True).first()
            if listing:
                StockMLRanker.evaluate_and_predict(listing)
                count += 1

        messages.success(request, f"Generated fresh statistical ML predictions for {count} universe leaders.")
        return redirect("ml_engine:dashboard")
