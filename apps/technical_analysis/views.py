from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.technical_analysis.models import TechnicalIndicatorSnapshot


class TechnicalOverviewView(HTMXResponseMixin, TemplateView):
    """
    Technical Analysis overview hub displaying signals, breakout alerts, and indicator summaries.
    """
    template_name = "technical_analysis/overview.html"
    partial_template_name = "technical_analysis/partials/overview_partial.html"
    active_nav = "technical_analysis"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Technical Analysis Intelligence"
        context["calculation_version"] = "tech-v2.0.0"

        latest_snapshots = (
            TechnicalIndicatorSnapshot.objects.select_related("listing__instrument", "listing__exchange")
            .order_by("-timestamp")
        )

        context["bullish_trends"] = latest_snapshots.filter(trend_signal="BULLISH")[:6]
        context["bearish_trends"] = latest_snapshots.filter(trend_signal="BEARISH")[:6]
        context["breakouts"] = latest_snapshots.exclude(breakout_signal="NEUTRAL")[:6]
        context["oversold_rsi"] = latest_snapshots.filter(rsi_signal="OVERSOLD")[:6]
        context["overbought_rsi"] = latest_snapshots.filter(rsi_signal="OVERBOUGHT")[:6]
        context["golden_crosses"] = latest_snapshots.filter(ma_cross_signal="GOLDEN_CROSS")[:6]
        return context
