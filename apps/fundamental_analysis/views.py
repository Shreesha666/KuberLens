from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.fundamental_analysis.models import FundamentalSnapshot


class FundamentalOverviewView(HTMXResponseMixin, TemplateView):
    """
    Fundamental Analysis overview hub displaying financial scoring leaders and valuation metrics.
    """
    template_name = "fundamental_analysis/overview.html"
    partial_template_name = "fundamental_analysis/partials/overview_partial.html"
    active_nav = "fundamental_analysis"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Fundamental Analysis & Valuation"
        context["calculation_version"] = "fund-v2.0.0"

        snapshots = (
            FundamentalSnapshot.objects.select_related("instrument")
            .order_by("-overall_score")
        )

        context["top_scored"] = snapshots[:6]
        context["value_picks"] = snapshots.filter(valuation_score__gte=70)[:6]
        context["growth_leaders"] = snapshots.filter(growth_score__gte=70)[:6]
        context["healthy_balance_sheets"] = snapshots.filter(financial_health_score__gte=75)[:6]
        return context
